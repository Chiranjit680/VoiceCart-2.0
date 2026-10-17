import { useState, useEffect, useRef } from "react";
import {
  Globe, CheckCircle2, Clock, AlertTriangle, ArrowRight,
  ExternalLink, Database, Wifi, WifiOff, Activity, Search,
  FileText, Link2, ShieldCheck, Loader2, BarChart3, Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/* ── Static crawl targets ── */
const CRAWL_TARGETS = [
  { url: "https://www.amazon.com/dp/B0CX23V2ZK", domain: "amazon.com", title: 'MacBook Pro 16" M3 Max — Amazon', status: "done" as const, pages: 12, links: 87, time: "2.4s" },
  { url: "https://www.bestbuy.com/site/iphone-16-pro-max", domain: "bestbuy.com", title: "iPhone 16 Pro Max — Best Buy", status: "done" as const, pages: 8, links: 54, time: "1.8s" },
  { url: "https://www.samsung.com/galaxy-s25-ultra", domain: "samsung.com", title: "Galaxy S25 Ultra — Samsung", status: "done" as const, pages: 15, links: 112, time: "3.1s" },
  { url: "https://electronics.sony.com/wh1000xm5", domain: "sony.com", title: "WH-1000XM5 Headphones — Sony", status: "done" as const, pages: 6, links: 39, time: "1.2s" },
  { url: "https://www.dell.com/xps-15-2025", domain: "dell.com", title: "XPS 15 (2025) — Dell", status: "running" as const, pages: 4, links: 28, time: "—" },
  { url: "https://www.apple.com/apple-watch-ultra-3", domain: "apple.com", title: "Apple Watch Ultra 3 — Apple", status: "queued" as const, pages: 0, links: 0, time: "—" },
  { url: "https://www.lg.com/oled-tv-c4", domain: "lg.com", title: 'LG C4 65" OLED — LG', status: "queued" as const, pages: 0, links: 0, time: "—" },
  { url: "https://store.playstation.com/ps5-pro", domain: "playstation.com", title: "PlayStation 5 Pro — PlayStation", status: "queued" as const, pages: 0, links: 0, time: "—" },
];

const CRAWL_STATS = {
  totalPages: 45,
  totalLinks: 320,
  productsFound: 38,
  priceChanges: 7,
  avgResponseTime: "1.6s",
  dataSize: "4.2 MB",
  uptime: "99.7%",
  lastSync: "2 min ago",
};

/* ── Fake live log entries ── */
const LOG_LINES = [
  { ts: "14:32:01", level: "info", msg: "[spider] Crawl session started — 8 targets queued" },
  { ts: "14:32:01", level: "info", msg: "[dns] Resolving amazon.com → 54.239.28.85" },
  { ts: "14:32:02", level: "ok", msg: "[http] GET https://www.amazon.com/dp/B0CX23V2ZK → 200 OK (342ms)" },
  { ts: "14:32:02", level: "info", msg: "[parse] Extracting product schema from DOM…" },
  { ts: "14:32:03", level: "ok", msg: "[extract] Found: MacBook Pro 16\" M3 Max — $2,499.00" },
  { ts: "14:32:03", level: "info", msg: "[link] Discovered 87 outbound links, 12 product pages" },
  { ts: "14:32:04", level: "ok", msg: "[store] Saved 12 pages → PostgreSQL (voicecart_crawl_data)" },
  { ts: "14:32:05", level: "info", msg: "[dns] Resolving bestbuy.com → 23.40.164.122" },
  { ts: "14:32:05", level: "ok", msg: "[http] GET https://www.bestbuy.com/site/iphone-16-pro-max → 200 OK (287ms)" },
  { ts: "14:32:06", level: "ok", msg: "[extract] Found: iPhone 16 Pro Max — $1,199.00" },
  { ts: "14:32:06", level: "warn", msg: "[rate-limit] bestbuy.com — throttling to 2 req/s (429 detected)" },
  { ts: "14:32:07", level: "ok", msg: "[store] Saved 8 pages → PostgreSQL" },
  { ts: "14:32:08", level: "info", msg: "[dns] Resolving samsung.com → 151.101.1.40" },
  { ts: "14:32:08", level: "ok", msg: "[http] GET https://www.samsung.com/galaxy-s25-ultra → 200 OK (512ms)" },
  { ts: "14:32:09", level: "info", msg: "[parse] JavaScript-rendered page — switching to headless Chromium" },
  { ts: "14:32:10", level: "ok", msg: "[extract] Found: Galaxy S25 Ultra — $1,299.99 (price drop: -$50)" },
  { ts: "14:32:10", level: "info", msg: "[diff] Price change detected vs last crawl — flagging for alert" },
  { ts: "14:32:11", level: "ok", msg: "[store] Saved 15 pages → PostgreSQL" },
  { ts: "14:32:12", level: "ok", msg: "[http] GET https://electronics.sony.com/wh1000xm5 → 200 OK (198ms)" },
  { ts: "14:32:12", level: "ok", msg: "[extract] Found: Sony WH-1000XM5 — $349.99" },
  { ts: "14:32:13", level: "ok", msg: "[store] Saved 6 pages → PostgreSQL" },
  { ts: "14:32:14", level: "info", msg: "[spider] 4/8 targets complete — starting dell.com" },
  { ts: "14:32:14", level: "ok", msg: "[http] GET https://www.dell.com/xps-15-2025 → 200 OK (623ms)" },
  { ts: "14:32:15", level: "info", msg: "[parse] Extracting product data from dell.com…" },
  { ts: "14:32:16", level: "info", msg: "[crawl] Processing page 4 of dell.com — following pagination…" },
];

function StatusIcon({ status }: { status: "done" | "running" | "queued" }) {
  switch (status) {
    case "done":
      return <CheckCircle2 className="h-4 w-4 text-emerald-500" />;
    case "running":
      return <Loader2 className="h-4 w-4 text-blue-400 animate-spin" />;
    case "queued":
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
}

function LogLevel({ level }: { level: string }) {
  const cls =
    level === "ok" ? "text-emerald-400" :
    level === "warn" ? "text-amber-400" :
    level === "error" ? "text-red-400" :
    "text-blue-400";
  return <span className={`font-semibold uppercase text-[11px] ${cls}`}>{level.padEnd(4)}</span>;
}

export default function CrawlerPage() {
  const [visibleLogs, setVisibleLogs] = useState<typeof LOG_LINES>([]);
  const logRef = useRef<HTMLDivElement>(null);

  /* Simulate live log streaming */
  useEffect(() => {
    let idx = 0;
    const interval = setInterval(() => {
      if (idx < LOG_LINES.length) {
        setVisibleLogs((prev) => [...prev, LOG_LINES[idx]]);
        idx++;
      } else {
        clearInterval(interval);
      }
    }, 600);
    return () => clearInterval(interval);
  }, []);

  /* Auto-scroll log */
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [visibleLogs]);

  const doneCount = CRAWL_TARGETS.filter((t) => t.status === "done").length;
  const runningCount = CRAWL_TARGETS.filter((t) => t.status === "running").length;

  return (
    <div className="p-6 lg:p-8 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-foreground flex items-center gap-3">
            <Globe className="h-8 w-8 text-primary" />
            Web Crawler
          </h1>
          <p className="mt-1 text-muted-foreground">
            Real-time product data pipeline — scraping prices, specs & availability
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className="gap-1.5 text-xs border-emerald-500/50 text-emerald-500">
            <Wifi className="h-3 w-3" /> Connected
          </Badge>
          <Badge variant="outline" className="gap-1.5 text-xs">
            <Activity className="h-3 w-3" /> {doneCount}/{CRAWL_TARGETS.length} done
          </Badge>
        </div>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Pages Crawled", value: CRAWL_STATS.totalPages, icon: FileText, color: "text-blue-400" },
          { label: "Links Discovered", value: CRAWL_STATS.totalLinks, icon: Link2, color: "text-purple-400" },
          { label: "Products Found", value: CRAWL_STATS.productsFound, icon: Search, color: "text-emerald-400" },
          { label: "Price Changes", value: CRAWL_STATS.priceChanges, icon: BarChart3, color: "text-amber-400" },
        ].map((s) => (
          <Card key={s.label} className="bg-card">
            <CardContent className="flex items-center gap-3 p-4">
              <div className={`rounded-lg bg-muted p-2.5 ${s.color}`}>
                <s.icon className="h-5 w-5" />
              </div>
              <div>
                <p className="text-2xl font-bold text-foreground">{s.value}</p>
                <p className="text-[11px] text-muted-foreground">{s.label}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Pipeline info bar */}
      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-border bg-card px-5 py-3 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5"><Database className="h-3.5 w-3.5" /> PostgreSQL</span>
        <span className="text-border">|</span>
        <span className="flex items-center gap-1.5"><Zap className="h-3.5 w-3.5" /> Avg {CRAWL_STATS.avgResponseTime}</span>
        <span className="text-border">|</span>
        <span className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> Uptime {CRAWL_STATS.uptime}</span>
        <span className="text-border">|</span>
        <span>{CRAWL_STATS.dataSize} scraped</span>
        <span className="text-border">|</span>
        <span>Last sync: {CRAWL_STATS.lastSync}</span>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Crawl Targets — left 3 cols */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Globe className="h-4 w-4 text-primary" /> Crawl Queue
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
            {CRAWL_TARGETS.map((t) => (
              <div
                key={t.url}
                className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors ${
                  t.status === "running" ? "border-blue-500/40 bg-blue-500/5" : "border-border bg-card"
                }`}
              >
                <StatusIcon status={t.status} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{t.title}</p>
                  <p className="text-[11px] text-muted-foreground truncate flex items-center gap-1">
                    <ExternalLink className="h-3 w-3 shrink-0" /> {t.domain}
                  </p>
                  {t.status !== "queued" && (
                    <div className="mt-1 flex items-center gap-3 text-[11px] text-muted-foreground">
                      <span>{t.pages} pages</span>
                      <span>{t.links} links</span>
                      <span>{t.time}</span>
                    </div>
                  )}
                </div>
                <Badge
                  variant={t.status === "done" ? "default" : t.status === "running" ? "secondary" : "outline"}
                  className="shrink-0 text-[10px]"
                >
                  {t.status === "done" ? "Complete" : t.status === "running" ? "Crawling…" : "Queued"}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Live Log — right 3 cols */}
        <Card className="lg:col-span-3">
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <Activity className="h-4 w-4 text-emerald-400" />
              Live Crawl Log
              {runningCount > 0 && (
                <span className="ml-auto flex items-center gap-1.5 text-[11px] font-normal text-muted-foreground">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                  </span>
                  streaming
                </span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div
              ref={logRef}
              className="h-[380px] overflow-y-auto rounded-lg bg-[#0d1117] border border-[#1e2733] p-4 font-mono text-[12px] leading-relaxed"
            >
              {visibleLogs.length === 0 && (
                <span className="text-muted-foreground animate-pulse">Initializing crawler…</span>
              )}
              {visibleLogs.map((l, i) => (
                <div key={i} className="flex gap-2">
                  <span className="text-muted-foreground/60 shrink-0">{l.ts}</span>
                  <LogLevel level={l.level} />
                  <span className="text-gray-300">{l.msg}</span>
                </div>
              ))}
              {visibleLogs.length < LOG_LINES.length && (
                <span className="inline-block w-2 h-4 bg-emerald-400 animate-pulse ml-1" />
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
