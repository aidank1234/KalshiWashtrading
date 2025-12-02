import * as fs from "fs";
import * as path from "path";
import { execSync } from "child_process";

interface KalshiTrade {
  ticker_name: string;
  report_ticker: string;
  date: string;
  create_ts: string;
  contracts_traded: number;
  price: number;
}

interface DownloadResult {
  date: string;
  success: boolean;
  tradeCount: number;
}

const BASE_URL =
  "https://kalshi-public-docs.s3.amazonaws.com/reporting/trade_data_";

async function fetchDayData(dateStr: string): Promise<KalshiTrade[] | null> {
  const url = `${BASE_URL}${dateStr}.json`;

  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(30000),
    });

    if (!response.ok) {
      return null;
    }

    const data = await response.json();
    return data as KalshiTrade[];
  } catch (error) {
    return null;
  }
}

function formatDate(date: Date): string {
  return date.toISOString().split("T")[0];
}

function getDateRange(startDate: string, endDate: string): string[] {
  const dates: string[] = [];
  const current = new Date(startDate);
  const end = new Date(endDate);

  while (current <= end) {
    dates.push(formatDate(current));
    current.setDate(current.getDate() + 1);
  }

  return dates;
}

async function downloadAllHistory(
  startDate: string = "2021-07-01",
  outputDir: string = "./data"
): Promise<void> {
  // Create output directory
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  // End date is yesterday
  const yesterday = new Date();
  yesterday.setDate(yesterday.getDate() - 1);
  const endDate = formatDate(yesterday);

  console.log(`\n📊 Kalshi Historical Trade Data Downloader`);
  console.log(`==========================================`);
  console.log(`Start date: ${startDate}`);
  console.log(`End date:   ${endDate}`);
  console.log(`Output:     ${outputDir}\n`);

  const dates = getDateRange(startDate, endDate);
  console.log(`Total days to fetch: ${dates.length}\n`);

  const results: DownloadResult[] = [];
  let totalTrades = 0;
  let successCount = 0;

  // Process in batches to avoid overwhelming the server
  const BATCH_SIZE = 10;
  const DELAY_MS = 100;

  for (let i = 0; i < dates.length; i += BATCH_SIZE) {
    const batch = dates.slice(i, i + BATCH_SIZE);

    const batchPromises = batch.map(async (dateStr) => {
      const data = await fetchDayData(dateStr);

      if (data && data.length > 0) {
        // Save individual day file
        const dayFile = path.join(outputDir, `trades_${dateStr}.json`);
        fs.writeFileSync(dayFile, JSON.stringify(data));

        return {
          date: dateStr,
          success: true,
          tradeCount: data.length,
        };
      }

      return {
        date: dateStr,
        success: false,
        tradeCount: 0,
      };
    });

    const batchResults = await Promise.all(batchPromises);

    for (const result of batchResults) {
      results.push(result);
      if (result.success) {
        successCount++;
        totalTrades += result.tradeCount;
      }
    }

    // Progress update
    const progress = Math.min(i + BATCH_SIZE, dates.length);
    process.stdout.write(
      `\rProgress: ${progress}/${dates.length} days | Success: ${successCount} | Trades: ${totalTrades.toLocaleString()}`
    );

    // Small delay between batches
    await new Promise((resolve) => setTimeout(resolve, DELAY_MS));
  }

  console.log(`\n\n✅ Download complete!`);
  console.log(`   Successful days: ${successCount}`);
  console.log(`   Total trades:    ${totalTrades.toLocaleString()}`);

  // Save metadata
  const metadata = {
    downloadedAt: new Date().toISOString(),
    startDate,
    endDate,
    totalDays: dates.length,
    successfulDays: successCount,
    totalTrades,
    results: results.filter((r) => r.success),
  };

  fs.writeFileSync(
    path.join(outputDir, "metadata.json"),
    JSON.stringify(metadata, null, 2)
  );

  console.log(`\n📁 Metadata saved to ${path.join(outputDir, "metadata.json")}`);
}

// Combine all daily files using shell - Node can't handle this much data
async function combineToSingleFile(
  inputDir: string = "./data",
  outputFile: string = "./data/all_trades.csv"
): Promise<void> {
  console.log(`\n🔗 Combining all daily files using shell...`);

  const files = fs
    .readdirSync(inputDir)
    .filter((f) => f.startsWith("trades_") && f.endsWith(".json"))
    .sort();

  console.log(`Found ${files.length} daily files`);

  // Write header
  fs.writeFileSync(outputFile, "ticker_name,report_ticker,date,create_ts,contracts_traded,price\n");

  // Process each file with jq and append to CSV
  let filesProcessed = 0;

  for (const file of files) {
    const filePath = path.join(inputDir, file);
    try {
      // Use jq to convert JSON to CSV lines, append to output
      execSync(
        `cat "${filePath}" | jq -r '.[] | [.ticker_name, .report_ticker, .date, .create_ts, .contracts_traded, .price] | @csv' >> "${outputFile}"`,
        { stdio: "pipe" }
      );
      filesProcessed++;
      if (filesProcessed % 50 === 0) {
        process.stdout.write(`\rProcessed ${filesProcessed}/${files.length} files`);
      }
    } catch (e) {
      // If jq not available, fall back to simple JSON parse per file
      try {
        const data: KalshiTrade[] = JSON.parse(fs.readFileSync(filePath, "utf-8"));
        const lines = data.map(t => 
          `"${t.ticker_name}","${t.report_ticker}","${t.date}","${t.create_ts}",${t.contracts_traded},${t.price}`
        ).join("\n") + "\n";
        fs.appendFileSync(outputFile, lines);
        filesProcessed++;
        if (filesProcessed % 50 === 0) {
          process.stdout.write(`\rProcessed ${filesProcessed}/${files.length} files`);
        }
      } catch (e2) {
        console.error(`\nError processing ${file}: ${e2}`);
      }
    }
  }

  // Count lines
  const lineCount = execSync(`wc -l < "${outputFile}"`).toString().trim();
  
  console.log(`\n\n✅ Combined CSV saved to ${outputFile}`);
  console.log(`   Total lines: ${parseInt(lineCount).toLocaleString()} (including header)`);
  console.log(`   Files processed: ${filesProcessed}`);
}

// Quick test function to check data shape
async function testFetch(): Promise<void> {
  console.log(`\n🧪 Testing data fetch...\n`);

  // Try a recent date
  const testDate = "2025-09-07";
  console.log(`Fetching ${testDate}...`);

  const data = await fetchDayData(testDate);

  if (!data) {
    console.log(`❌ Failed to fetch data for ${testDate}`);
    return;
  }

  console.log(`✅ Success! Got ${data.length.toLocaleString()} trades\n`);

  console.log(`📋 Data shape:`);
  console.log(`   Fields: ${Object.keys(data[0]).join(", ")}`);

  console.log(`\n📊 Sample trades (first 5):`);
  for (const trade of data.slice(0, 5)) {
    console.log(`   ${trade.ticker_name} | ${trade.contracts_traded} contracts @ ${trade.price}¢ | ${trade.create_ts}`);
  }

  // Basic stats
  const totalVolume = data.reduce((sum, t) => sum + t.contracts_traded, 0);
  const uniqueTickers = new Set(data.map((t) => t.ticker_name)).size;
  const uniqueReportTickers = new Set(data.map((t) => t.report_ticker)).size;

  console.log(`\n📈 Day summary:`);
  console.log(`   Total trades:      ${data.length.toLocaleString()}`);
  console.log(`   Total contracts:   ${totalVolume.toLocaleString()}`);
  console.log(`   Unique tickers:    ${uniqueTickers.toLocaleString()}`);
  console.log(`   Unique categories: ${uniqueReportTickers}`);

  // Price distribution
  const extremePrices = data.filter((t) => t.price <= 5 || t.price >= 95);
  console.log(`   Extreme price trades (<5¢ or >95¢): ${extremePrices.length} (${((extremePrices.length / data.length) * 100).toFixed(1)}%)`);
}

// Main execution
const args = process.argv.slice(2);
const command = args[0] || "test";

if (command === "test") {
  testFetch();
} else if (command === "download") {
  const startDate = args[1] || "2021-07-01";
  downloadAllHistory(startDate);
} else if (command === "combine") {
  combineToSingleFile();
} else {
  console.log(`
Usage:
  npx ts-node src/downloadHistory.ts test              # Test fetch and see data shape
  npx ts-node src/downloadHistory.ts download [date]   # Download all history from date
  npx ts-node src/downloadHistory.ts combine           # Combine daily files into one
`);
}

export { downloadAllHistory, combineToSingleFile, testFetch, KalshiTrade };

