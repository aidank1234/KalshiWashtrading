#!/usr/bin/env python3
"""Generate charts for Kalshi wash trading analysis."""

import duckdb
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

# Set style
plt.style.use('seaborn-v0_8-darkgrid')
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.size'] = 11
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['axes.titleweight'] = 'bold'

DATA_PATH = Path(__file__).parent.parent / 'data' / 'all_trades.parquet'
CHARTS_PATH = Path(__file__).parent.parent / 'charts'
CHARTS_PATH.mkdir(exist_ok=True)

def get_connection():
    return duckdb.connect()

# ============================================================================
# Chart: Hourly Trading Pattern (Bitcoin Daily vs NFL)
# ============================================================================
def chart_hourly_pattern():
    conn = get_connection()
    
    query = f"""
    SELECT 
        EXTRACT(HOUR FROM create_ts::TIMESTAMP) as hour,
        CASE 
            WHEN report_ticker LIKE 'KXBTCD%' THEN 'Bitcoin Daily'
            WHEN report_ticker LIKE 'KXNFL%' THEN 'NFL'
            ELSE NULL
        END as market,
        COUNT(*) as trades
    FROM '{DATA_PATH}'
    WHERE create_ts::TIMESTAMP >= '2025-01-01'
      AND (report_ticker LIKE 'KXBTCD%' OR report_ticker LIKE 'KXNFL%')
    GROUP BY hour, market
    ORDER BY hour
    """
    
    df = conn.execute(query).fetchdf()
    
    btc = df[df['market'] == 'Bitcoin Daily'].sort_values('hour')
    nfl = df[df['market'] == 'NFL'].sort_values('hour')
    
    # Normalize to percentages of each market's total
    btc_pct = btc['trades'] / btc['trades'].sum() * 100
    nfl_pct = nfl['trades'] / nfl['trades'].sum() * 100
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    hours = range(24)
    
    ax.fill_between(hours, nfl_pct, alpha=0.3, color='#3498db', label='NFL')
    ax.plot(hours, nfl_pct, color='#3498db', linewidth=2)
    
    ax.fill_between(hours, btc_pct, alpha=0.3, color='#e74c3c', label='Bitcoin Daily')
    ax.plot(hours, btc_pct, color='#e74c3c', linewidth=2)
    
    # Highlight overnight hours (midnight to 6 AM)
    ax.axvspan(0, 6, alpha=0.1, color='gray', label='Overnight (US)')
    
    # Mark 4 AM specifically
    ax.axvline(x=4, color='#e74c3c', linestyle='--', alpha=0.7, linewidth=1.5)
    ax.annotate('4 AM\n(Black Friday spike)', xy=(4, btc_pct.iloc[4]), 
                xytext=(6, btc_pct.iloc[4] + 1.5),
                fontsize=9, color='#e74c3c',
                arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1))
    
    ax.set_xlabel('Hour of Day (Eastern Time)')
    ax.set_ylabel('% of Daily Trades')
    ax.set_title('When Trading Happens: Bitcoin Daily vs NFL (2025)')
    ax.set_xticks(range(0, 24, 2))
    ax.set_xticklabels([f'{h}:00' for h in range(0, 24, 2)])
    ax.legend(loc='upper right')
    ax.set_xlim(0, 23)
    
    plt.tight_layout()
    plt.savefig(CHARTS_PATH / 'hourly_pattern.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated: hourly_pattern.png")

# ============================================================================
# Chart: Monthly Repetitive Rate Trend
# ============================================================================
def chart_monthly_trend():
    conn = get_connection()
    
    query = f"""
    WITH trade_patterns AS (
        SELECT 
            strftime(create_ts::TIMESTAMP, '%Y-%m') as month,
            contracts_traded,
            LAG(contracts_traded) OVER (PARTITION BY ticker_name ORDER BY create_ts) as prev_size,
            LEAD(contracts_traded) OVER (PARTITION BY ticker_name ORDER BY create_ts) as next_size,
            EXTRACT(EPOCH FROM (create_ts::TIMESTAMP - LAG(create_ts::TIMESTAMP) OVER (PARTITION BY ticker_name ORDER BY create_ts))) as gap
        FROM '{DATA_PATH}'
        WHERE report_ticker LIKE 'KXBTCD%' AND create_ts::TIMESTAMP >= '2025-01-01'
    )
    SELECT 
        month,
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE contracts_traded = prev_size AND contracts_traded = next_size AND gap BETWEEN 1 AND 60) as repetitive
    FROM trade_patterns
    GROUP BY month
    ORDER BY month
    """
    
    df = conn.execute(query).fetchdf()
    df['rate'] = df['repetitive'] / df['total'] * 100
    
    fig, ax1 = plt.subplots(figsize=(12, 6))
    
    x = range(len(df))
    
    # Primary axis: repetitive rate
    color1 = '#e74c3c'
    ax1.plot(x, df['rate'], color=color1, linewidth=2.5, marker='o', markersize=8, label='Repetitive Rate')
    ax1.fill_between(x, df['rate'], alpha=0.2, color=color1)
    ax1.set_xlabel('Month')
    ax1.set_ylabel('Repetitive Rate (%)', color=color1)
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.set_ylim(0, max(df['rate']) * 1.2)
    
    # Secondary axis: total trades
    ax2 = ax1.twinx()
    color2 = '#3498db'
    ax2.bar(x, df['total'] / 1000, alpha=0.3, color=color2, label='Total Trades (K)')
    ax2.set_ylabel('Total Trades (thousands)', color=color2)
    ax2.tick_params(axis='y', labelcolor=color2)
    
    # X-axis labels
    months = [m.split('-')[1] + '/' + m.split('-')[0][2:] for m in df['month']]
    ax1.set_xticks(x)
    ax1.set_xticklabels(months)
    
    ax1.set_title('Bitcoin Daily: Repetitive Rate Over Time (2025)')
    
    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    plt.tight_layout()
    plt.savefig(CHARTS_PATH / 'monthly_trend.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated: monthly_trend.png")

# ============================================================================
# Chart 1: Repetitive Rate by Market Type
# ============================================================================
def chart_repetitive_by_market():
    conn = get_connection()
    
    query = f"""
    WITH trade_patterns AS (
        SELECT 
            CASE 
                WHEN report_ticker LIKE 'KXNFL%' THEN 'NFL'
                WHEN report_ticker LIKE 'KXNCAAF%' THEN 'NCAA Football'
                WHEN report_ticker LIKE 'KXNBA%' THEN 'NBA'
                WHEN report_ticker LIKE 'KXMLB%' THEN 'MLB'
                WHEN report_ticker LIKE 'KXMARMAD%' THEN 'March Madness'
                WHEN report_ticker LIKE 'KXBTCD%' THEN 'Bitcoin Daily'
                WHEN report_ticker LIKE 'KXATP%' THEN 'Tennis'
                WHEN report_ticker = 'KXFEDDECISION' THEN 'Fed Decisions'
                WHEN report_ticker LIKE 'KXPGA%' THEN 'Golf'
                ELSE 'Other'
            END as market,
            contracts_traded,
            LAG(contracts_traded) OVER (PARTITION BY ticker_name ORDER BY create_ts) as prev_size,
            LEAD(contracts_traded) OVER (PARTITION BY ticker_name ORDER BY create_ts) as next_size,
            EXTRACT(EPOCH FROM (create_ts::TIMESTAMP - LAG(create_ts::TIMESTAMP) OVER (PARTITION BY ticker_name ORDER BY create_ts))) as gap
        FROM '{DATA_PATH}'
        WHERE create_ts::TIMESTAMP >= '2025-01-01'
    )
    SELECT 
        market,
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE contracts_traded = prev_size AND contracts_traded = next_size AND gap BETWEEN 1 AND 60) as repetitive
    FROM trade_patterns
    WHERE market != 'Other'
    GROUP BY market
    HAVING COUNT(*) > 100000
    ORDER BY (COUNT(*) FILTER (WHERE contracts_traded = prev_size AND contracts_traded = next_size AND gap BETWEEN 1 AND 60))::FLOAT / COUNT(*) DESC
    """
    
    df = conn.execute(query).fetchdf()
    df['rate'] = df['repetitive'] / df['total'] * 100
    
    # Create figure
    fig, ax = plt.subplots(figsize=(10, 6))
    
    colors = ['#e74c3c' if rate > 2 else '#3498db' if rate > 0.5 else '#2ecc71' 
              for rate in df['rate']]
    
    bars = ax.barh(df['market'], df['rate'], color=colors, edgecolor='white', linewidth=0.5)
    
    # Add value labels
    for bar, rate in zip(bars, df['rate']):
        ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height()/2, 
                f'{rate:.2f}%', va='center', fontsize=10)
    
    ax.set_xlabel('Repetitive Trade Rate (%)')
    ax.set_title('Repetitive Trading Patterns by Market Type (2025)')
    ax.set_xlim(0, max(df['rate']) * 1.2)
    
    # Legend
    red_patch = mpatches.Patch(color='#e74c3c', label='Elevated (>2%)')
    blue_patch = mpatches.Patch(color='#3498db', label='Moderate (0.5-2%)')
    green_patch = mpatches.Patch(color='#2ecc71', label='Normal (<0.5%)')
    ax.legend(handles=[red_patch, blue_patch, green_patch], loc='lower right')
    
    plt.tight_layout()
    plt.savefig(CHARTS_PATH / 'repetitive_by_market.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated: repetitive_by_market.png")

# ============================================================================
# Chart 2: Bitcoin Daily - Repetitive Rate by Trade Size
# ============================================================================
def chart_btc_size_distribution():
    conn = get_connection()
    
    query = f"""
    WITH trade_patterns AS (
        SELECT 
            contracts_traded,
            LAG(contracts_traded) OVER (PARTITION BY ticker_name ORDER BY create_ts) as prev_size,
            LEAD(contracts_traded) OVER (PARTITION BY ticker_name ORDER BY create_ts) as next_size,
            EXTRACT(EPOCH FROM (create_ts::TIMESTAMP - LAG(create_ts::TIMESTAMP) OVER (PARTITION BY ticker_name ORDER BY create_ts))) as gap
        FROM '{DATA_PATH}'
        WHERE report_ticker LIKE 'KXBTCD%' AND create_ts::TIMESTAMP >= '2025-01-01'
    )
    SELECT 
        contracts_traded as size,
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE contracts_traded = prev_size AND contracts_traded = next_size AND gap BETWEEN 1 AND 60) as repetitive
    FROM trade_patterns
    WHERE contracts_traded IN (1, 2, 3, 5, 10, 25, 50, 100)
    GROUP BY contracts_traded
    ORDER BY contracts_traded
    """
    
    df = conn.execute(query).fetchdf()
    df['rate'] = df['repetitive'] / df['total'] * 100
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(df))
    width = 0.6
    
    colors = ['#e74c3c' if rate > 10 else '#f39c12' if rate > 5 else '#3498db' 
              for rate in df['rate']]
    
    bars = ax.bar(x, df['rate'], width, color=colors, edgecolor='white', linewidth=0.5)
    
    # Add value labels on bars
    for bar, rate, total in zip(bars, df['rate'], df['total']):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f'{rate:.1f}%', ha='center', va='bottom', fontsize=10, fontweight='bold')
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height()/2,
                f'{total:,}', ha='center', va='center', fontsize=8, color='white')
    
    ax.set_xlabel('Trade Size (contracts)')
    ax.set_ylabel('Repetitive Rate (%)')
    ax.set_title('Bitcoin Daily: Repetitive Rate by Trade Size')
    ax.set_xticks(x)
    ax.set_xticklabels(df['size'].astype(str))
    ax.set_ylim(0, max(df['rate']) * 1.2)
    
    plt.tight_layout()
    plt.savefig(CHARTS_PATH / 'btc_size_distribution.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated: btc_size_distribution.png")

# ============================================================================
# Chart 3: Trade Timing Gaps (Bitcoin Daily)
# ============================================================================
def chart_timing_distribution():
    conn = get_connection()
    
    query = f"""
    WITH gaps AS (
        SELECT 
            EXTRACT(EPOCH FROM (create_ts::TIMESTAMP - LAG(create_ts::TIMESTAMP) OVER (PARTITION BY ticker_name ORDER BY create_ts))) as gap_seconds
        FROM '{DATA_PATH}'
        WHERE report_ticker LIKE 'KXBTCD%' 
          AND create_ts::TIMESTAMP >= '2025-01-01'
          AND contracts_traded = 1
    )
    SELECT 
        CASE 
            WHEN gap_seconds < 1 THEN '0 (same second)'
            WHEN gap_seconds < 2 THEN '1 second'
            WHEN gap_seconds < 3 THEN '2 seconds'
            WHEN gap_seconds < 5 THEN '3-4 seconds'
            WHEN gap_seconds < 10 THEN '5-9 seconds'
            WHEN gap_seconds < 30 THEN '10-29 seconds'
            WHEN gap_seconds < 60 THEN '30-59 seconds'
            ELSE '60+ seconds'
        END as gap_bucket,
        COUNT(*) as count
    FROM gaps
    WHERE gap_seconds IS NOT NULL AND gap_seconds >= 0
    GROUP BY gap_bucket
    ORDER BY 
        CASE gap_bucket
            WHEN '0 (same second)' THEN 1
            WHEN '1 second' THEN 2
            WHEN '2 seconds' THEN 3
            WHEN '3-4 seconds' THEN 4
            WHEN '5-9 seconds' THEN 5
            WHEN '10-29 seconds' THEN 6
            WHEN '30-59 seconds' THEN 7
            ELSE 8
        END
    """
    
    df = conn.execute(query).fetchdf()
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    colors = ['#e74c3c', '#e74c3c', '#f39c12', '#f39c12', '#3498db', '#3498db', '#3498db', '#2ecc71']
    
    bars = ax.bar(range(len(df)), df['count'], color=colors[:len(df)], edgecolor='white', linewidth=0.5)
    
    # Add value labels
    for bar, count in zip(bars, df['count']):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1000,
                f'{count:,}', ha='center', va='bottom', fontsize=9, rotation=45)
    
    ax.set_xlabel('Gap Between Consecutive Size-1 Trades')
    ax.set_ylabel('Number of Trades')
    ax.set_title('Bitcoin Daily: Time Gaps Between Size-1 Trades (2025)')
    ax.set_xticks(range(len(df)))
    ax.set_xticklabels(df['gap_bucket'], rotation=45, ha='right')
    
    plt.tight_layout()
    plt.savefig(CHARTS_PATH / 'timing_distribution.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated: timing_distribution.png")

# ============================================================================
# Chart 4: Volume Share Pie Chart
# ============================================================================
def chart_volume_share():
    conn = get_connection()
    
    query = f"""
    SELECT 
        CASE 
            WHEN report_ticker LIKE 'KXNFL%' THEN 'NFL'
            WHEN report_ticker LIKE 'KXNCAAF%' THEN 'NCAA Football'
            WHEN report_ticker LIKE 'KXNBA%' THEN 'NBA'
            WHEN report_ticker LIKE 'KXMLB%' THEN 'MLB'
            WHEN report_ticker LIKE 'KXMARMAD%' THEN 'March Madness'
            WHEN report_ticker LIKE 'KXBTCD%' THEN 'Bitcoin Daily'
            WHEN report_ticker LIKE 'KXATP%' THEN 'Tennis'
            WHEN report_ticker = 'KXFEDDECISION' THEN 'Fed Decisions'
            WHEN report_ticker LIKE 'KXPGA%' THEN 'Golf'
            ELSE 'Other'
        END as market,
        SUM(contracts_traded) as volume
    FROM '{DATA_PATH}'
    WHERE create_ts::TIMESTAMP >= '2025-01-01'
    GROUP BY market
    ORDER BY volume DESC
    """
    
    df = conn.execute(query).fetchdf()
    
    # Combine smaller categories
    threshold = df['volume'].sum() * 0.02
    main = df[df['volume'] >= threshold].copy()
    other_vol = df[df['volume'] < threshold]['volume'].sum()
    
    if other_vol > 0:
        main = main._append({'market': 'Other', 'volume': other_vol}, ignore_index=True)
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Custom colors - highlight Bitcoin Daily
    colors = []
    for market in main['market']:
        if market == 'Bitcoin Daily':
            colors.append('#e74c3c')
        elif market == 'Fed Decisions':
            colors.append('#f39c12')
        elif market == 'Other':
            colors.append('#95a5a6')
        else:
            colors.append(plt.cm.Blues(0.3 + 0.5 * (list(main['market']).index(market) / len(main))))
    
    explode = [0.05 if m == 'Bitcoin Daily' else 0 for m in main['market']]
    
    wedges, texts, autotexts = ax.pie(
        main['volume'], 
        labels=main['market'],
        autopct=lambda pct: f'{pct:.1f}%' if pct > 2 else '',
        colors=colors,
        explode=explode,
        startangle=90,
        pctdistance=0.75
    )
    
    ax.set_title('Kalshi 2025 Volume by Market Type')
    
    plt.tight_layout()
    plt.savefig(CHARTS_PATH / 'volume_share.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated: volume_share.png")

# ============================================================================
# Chart 5: Comparison - Sports vs Crypto Repetitive Rates
# ============================================================================
def chart_sports_vs_crypto():
    conn = get_connection()
    
    query = f"""
    WITH trade_patterns AS (
        SELECT 
            CASE 
                WHEN report_ticker LIKE 'KXNFL%' THEN 'NFL'
                WHEN report_ticker LIKE 'KXNCAAF%' THEN 'NCAA FB'
                WHEN report_ticker LIKE 'KXNBA%' THEN 'NBA'
                WHEN report_ticker LIKE 'KXMLB%' THEN 'MLB'
                WHEN report_ticker LIKE 'KXBTCD%' THEN 'Bitcoin Daily'
                ELSE NULL
            END as market,
            CASE 
                WHEN report_ticker LIKE 'KXBTCD%' THEN 'Crypto'
                ELSE 'Sports'
            END as category,
            contracts_traded,
            LAG(contracts_traded) OVER (PARTITION BY ticker_name ORDER BY create_ts) as prev_size,
            LEAD(contracts_traded) OVER (PARTITION BY ticker_name ORDER BY create_ts) as next_size,
            EXTRACT(EPOCH FROM (create_ts::TIMESTAMP - LAG(create_ts::TIMESTAMP) OVER (PARTITION BY ticker_name ORDER BY create_ts))) as gap
        FROM '{DATA_PATH}'
        WHERE create_ts::TIMESTAMP >= '2025-01-01'
    )
    SELECT 
        market,
        category,
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE contracts_traded = prev_size AND contracts_traded = next_size AND gap BETWEEN 1 AND 60) as repetitive
    FROM trade_patterns
    WHERE market IS NOT NULL
    GROUP BY market, category
    """
    
    df = conn.execute(query).fetchdf()
    df['rate'] = df['repetitive'] / df['total'] * 100
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    sports = df[df['category'] == 'Sports'].sort_values('rate')
    crypto = df[df['category'] == 'Crypto']
    
    # Combine for plotting
    all_markets = list(sports['market']) + list(crypto['market'])
    all_rates = list(sports['rate']) + list(crypto['rate'])
    colors = ['#3498db'] * len(sports) + ['#e74c3c'] * len(crypto)
    
    bars = ax.barh(all_markets, all_rates, color=colors, edgecolor='white', linewidth=0.5)
    
    # Add value labels
    for bar, rate in zip(bars, all_rates):
        ax.text(bar.get_width() + 0.05, bar.get_y() + bar.get_height()/2, 
                f'{rate:.2f}%', va='center', fontsize=10)
    
    # Add dividing line
    ax.axhline(y=len(sports) - 0.5, color='gray', linestyle='--', alpha=0.5)
    
    ax.set_xlabel('Repetitive Trade Rate (%)')
    ax.set_title('Sports Markets vs Bitcoin Daily: Repetitive Trading Comparison')
    ax.set_xlim(0, max(all_rates) * 1.3)
    
    # Legend
    sports_patch = mpatches.Patch(color='#3498db', label='Sports (Baseline)')
    crypto_patch = mpatches.Patch(color='#e74c3c', label='Crypto (Elevated)')
    ax.legend(handles=[sports_patch, crypto_patch], loc='lower right')
    
    # Add annotation
    ax.annotate('21x higher', xy=(crypto['rate'].values[0], len(sports)), 
                xytext=(crypto['rate'].values[0] - 1, len(sports) + 0.5),
                fontsize=10, color='#e74c3c', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#e74c3c', lw=1.5))
    
    plt.tight_layout()
    plt.savefig(CHARTS_PATH / 'sports_vs_crypto.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("✓ Generated: sports_vs_crypto.png")

# ============================================================================
# Main
# ============================================================================
if __name__ == '__main__':
    print("Generating charts...")
    print(f"Data path: {DATA_PATH}")
    print(f"Output path: {CHARTS_PATH}")
    print()
    
    # Core bar charts (most impactful)
    chart_repetitive_by_market()
    chart_btc_size_distribution()
    
    # Line/area charts
    chart_hourly_pattern()
    chart_monthly_trend()
    
    print()
    print("✅ All charts generated!")

