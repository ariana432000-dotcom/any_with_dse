"""
Simulated content for demo mode — realistic AAPL output so the interface and
the live streaming can be exercised without Ollama, Chroma, or TradingAgents.
This is illustrative sample text, not a market recommendation.
"""

INDICATORS = {"rsi": 61.4, "macd": 1.82, "close_50_sma": 222.6, "boll_ub": 238.9, "boll_lb": 210.3}
REGIME = "TRENDING_BULL"

STOCK_CSV = "\n".join([
    "Date,Open,High,Low,Close,Volume",
    "2026-06-16,229.1,231.4,227.8,230.2,41200000",
    "2026-06-17,230.5,233.0,229.6,232.7,38900000",
    "2026-06-18,232.9,235.1,231.2,234.4,44100000",
    "2026-06-19,234.0,236.2,232.5,235.8,39750000",
])

FUND_METRICS = {
    "market_cap": "$3.52B".replace("B", "T"), "pe_ratio": "31.4", "eps_ttm": "7.46",
    "revenue_ttm": "$408.6B", "beta": "1.21", "dividend_yield": "0.42",
    "52w_high": "245.2", "52w_low": "181.0", "50d_sma": "222.6",
    "free_cash_flow_q": "$28.4B", "net_debt": "$52.1B",
}
NEWS_METRICS = {"positive_count": 3, "negative_count": 1, "neutral_count": 2, "overall_sentiment": "POSITIVE"}
SENT_METRICS = {"score": "7", "confidence": "Medium", "overall": "BULLISH"}

FUND_LOGS = ["Fetching fundamentals for AAPL on 2026-06-19", "calling get_fundamentals",
             "calling get_balance_sheet", "calling get_cashflow", "calling get_income_statement",
             "fundamentals report ready"]
MARKET_LOGS = ["Fetching market data for AAPL", "calling get_stock_data", "calling get_indicators",
               "market report ready"]
NEWS_LOGS = ["Fetching news for AAPL", "calling get_news", "calling get_global_news",
             "ingested 6 news chunks into RAG corpus", "news report ready"]

BACKFILL = ("Resolved **1** pending episode using the latest close **$235.80**.\n\n"
            "| Date | Signal | P&L | Outcome |\n|---|---|---|---|\n"
            "| 2026-06-17 | BUY | +2.14% | WIN |")

FUNDAMENTALS = """### Company Overview
AAPL trades at a market cap of **$3.52T** with a trailing P/E of **31.4** and EPS (TTM) of **$7.46**.
Revenue over the trailing twelve months is **$408.6B**, and the beta of **1.21** indicates slightly
above-market volatility.

### Profitability
Margins remain healthy, supported by strong services growth. Free cash flow for the most recent
quarter came in at **$28.4B**.

### Balance Sheet
Net debt stands at **$52.1B**, comfortably serviced given the cash-generation profile.

### Risks
Elevated valuation leaves limited margin for a demand miss; FX and supply concentration remain watch items.

### Outlook
Fundamentals are constructive but priced for continued execution.

| Metric | Value | Read |
|---|---|---|
| P/E (TTM) | 31.4 | Rich |
| EPS (TTM) | $7.46 | Strong |
| FCF (Q) | $28.4B | Robust |

FINAL TRANSACTION PROPOSAL: **HOLD**
"""

MARKET = """### Technical Snapshot
Price is riding above the 50-day SMA (**222.6**), with RSI at **61.4** — firm but not overbought — and
a positive MACD of **1.82**, consistent with an established uptrend. Price sits in the upper half of the
Bollinger band (210.3 – 238.9).

| Indicator | Value | Signal | Interpretation |
|---|---|---|---|
| RSI | 61.4 | Neutral-Bullish | Momentum intact, room before overbought |
| MACD | 1.82 | Bullish | Positive trend confirmation |
| 50-SMA | 222.6 | Support | Price above trend anchor |
| Boll Upper | 238.9 | Watch | Near-term resistance |
| Boll Lower | 210.3 | Support | Downside cushion |
"""

NEWS = """### Company News Summary
Coverage skews constructive: services momentum and a well-received hardware refresh dominate headlines,
with one supply-chain caution.

### Global Macro Trends
Rates steady; risk appetite firm into quarter-end.

### Sentiment Assessment
Overall **POSITIVE**.

| Category | Headline | Sentiment | Impact | Source |
|---|---|---|---|---|
| Product | Services revenue hits record | POSITIVE | High | Newswire |
| Supply | Component lead times ease | POSITIVE | Medium | Trade press |
| Risk | Regulatory probe in EU widens | NEGATIVE | Medium | Reuters |
| Macro | Rates held steady | NEUTRAL | Low | Central bank |
"""

SENTIMENT = """### Data Source Review
Signals aggregated from news tone and social chatter.

### Score Breakdown
Net tone is **bullish**, though conviction is moderate given the regulatory overhang.

| Source | Sentiment | Score (1-10) | Confidence | Key Signal |
|---|---|---|---|---|
| News tone | Positive | 7/10 | Medium | Services strength |
| Social | Positive | 7/10 | Medium | Refresh buzz |

Overall: **BULLISH**, 7/10, Medium confidence.
"""

INV_FACILITATOR = """**BULL WINS** — narrowly.

The bull case leans on durable services growth, an intact technical uptrend, and constructive news tone.
The bear correctly flags valuation and regulatory risk, but did not establish a near-term catalyst for
downside.

Recommendation: **HOLD** with a bullish lean, **Medium** confidence.
"""

REFLECTION = ("Decisions made during the prior OVERBOUGHT regime were mixed (one WIN at +2.1%, one FLAT). "
              "As we enter a TRENDING_BULL regime, momentum is more supportive, but the earlier overbought "
              "episode is a reminder to trail stops rather than chase strength.")

MEMORY_CONTEXT = """**Past episodes in TRENDING_BULL regime:**
- 2026-06-17: BUY · RSI 58.2, Outcome=WIN (P&L +2.14%)
- 2026-06-12: HOLD · RSI 55.9, Outcome=FLAT (P&L 0.0%)

**Regime-transition reflection:**
""" + REFLECTION

EPISODES = [
    {"trade_date": "2026-06-17", "regime": "TRENDING_BULL", "signal": "BUY", "rsi": "58.2",
     "outcome_status": "RESOLVED", "pnl_pct": "2.14", "outcome_label": "WIN", "distance": 0.121},
    {"trade_date": "2026-06-12", "regime": "TRENDING_BULL", "signal": "HOLD", "rsi": "55.9",
     "outcome_status": "RESOLVED", "pnl_pct": "0.0", "outcome_label": "FLAT", "distance": 0.188},
]

TRADER = """**Recommendation: HOLD**, tilt to accumulate on pullbacks toward the 50-day SMA (~222).

Rationale: the analyst consensus is constructive but valuation is full. Memory shows prior BUYs in this
regime resolved positively, yet the transition reflection cautions against chasing. Entry discipline
beats conviction here.

- Action: HOLD core, stage adds near 222
- Stop reference: below 210 (lower band)
- Take-profit zone: 239–245 (upper band / 52w high)
"""

RISK_FACILITATOR = """Most compelling perspective: **NEUTRAL**.

The aggressive case for pressing the uptrend is credible, but the conservative reminder about valuation
and the EU probe tempers position size.

- Position sizing: **50%** of intended allocation
- Stop-loss: 210 · Take-profit: 240
- Final risk rating: **MEDIUM**
"""

FINAL = """## Portfolio Manager — Final Decision

**FINAL TRANSACTION PROPOSAL: HOLD**

Weighing the bullish technical structure and positive news tone against a rich valuation and an open
regulatory question, and tailoring to an Aggressive investor profile, the desk issues a **HOLD** with a
constructive bias. Add on weakness toward the 50-day SMA; size to 50% per the risk facilitator.

| Element | Call |
|---|---|
| Signal | HOLD (bullish lean) |
| Position | 50% of target |
| Stop | 210 |
| Target | 240 |
| Risk | MEDIUM |

*Illustrative sample output (demo mode) — not investment advice.*
"""


MACRO_SNAPSHOT = {
    "vix": {"latest": 16.8, "avg": 18.2},
    "tnx": {"latest": 4.28, "avg": 4.35},
    "dxy": {"latest": 101.2, "avg": 101.9},
}
MACRO_REGIME = "RISK_ON_LOW_VOL"

MACRO_REPORT = """VIX at **16.8** (30d avg 18.2) sits in calm territory, well below the 25 fear-gauge
threshold, while the 10-year yield at **4.28%** is tracking slightly below its 30-day average of 4.35% —
consistent with a modest easing-rates bias. The dollar index is roughly flat at **101.2**. Taken together
this is a **risk-on, low-volatility** backdrop that favors staying invested in quality equities rather
than de-risking.
"""

POST_MORTEM = """- Across the last 6 RESOLVED episodes for AAPL (4 WIN / 2 LOSS), BUY signals issued during
  TRENDING_BULL regimes have outperformed BUY signals issued during OVERBOUGHT regimes (avg +2.4% vs -0.6%).
- The system has not been systematically over- or under-aggressive — win rate tracks close to 65%, in line
  with target.
- One LOSS followed an OVERBOUGHT RSI reading that was overridden by a BUY call; the pattern suggests
  weighting RSI extremes more heavily when the Fundamentals Analyst is only mildly bullish.
- **Process adjustment:** when RSI >= 70 and the Fundamentals verdict is HOLD (not a strong BUY), prefer
  trimming size rather than pressing full conviction.
"""

VERIFIER_RESULT = {
    "status": "VERIFIED",
    "final_signal": "HOLD",
    "effective_signal": "HOLD",
    "auto_overridden": False,
    "notes": (
        "Rule-based: no contradictions — RSI 61.4 and news sentiment POSITIVE are both consistent with "
        "a HOLD/bullish-lean call.\n"
        "Numeric check (code, non-LLM): all cited figures (RSI, MACD, P/E, EPS) match the raw data within "
        "tolerance.\n"
        "LLM semantic check (advisory, does NOT affect status): SIGNAL_CONSISTENT: YES — the decision's "
        "own reasoning (constructive but priced-for-execution) matches its HOLD action."
    ),
}


def investment_turns(r):
    if r == 1:
        return [
            ("bull", "Bull Analyst", "Services revenue just hit a record and the stock is holding above "
             "its 50-day SMA with positive MACD — the trend and the fundamentals agree. This is strength "
             "you lean into, not fade."),
            ("bear", "Bear Analyst", "A 31x P/E prices in flawless execution while an EU probe widens. "
             "One demand miss or an adverse ruling and the multiple compresses fast. The uptrend is late, "
             "not early."),
        ]
    return [
        ("bull", "Bull Analyst", "The regulatory risk is known and slow-moving; meanwhile free cash flow "
         "of $28B a quarter funds buybacks that support the floor. RSI at 61 leaves room to run."),
        ("bear", "Bear Analyst", "Buybacks don't fix a valuation air-pocket. Near the upper Bollinger "
         "band with beta above 1, the risk/reward at these levels is asymmetric to the downside."),
    ]


def risk_turns(r):
    base = [
        ("aggressive", "Aggressive", "Momentum is confirmed and news tone is positive — press the winner, "
         "size up toward 75%, and let the trend pay."),
        ("conservative", "Conservative", "Full valuation plus an open EU probe argues for capital "
         "preservation. Keep size modest, 25%, with a tight stop under 210."),
        ("neutral", "Neutral", "Split the difference: a 50% position captures upside while respecting the "
         "overhang. Trail the stop as price advances."),
    ]
    return base
