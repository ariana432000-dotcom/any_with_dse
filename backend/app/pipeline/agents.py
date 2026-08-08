"""
The agent team — a faithful port of every `create_*` factory in the notebook.

Each factory takes an LLM and returns a `node(state)` callable that reads from a
shared state dict and returns updates, exactly as in the notebook. TradingAgents
tools are imported lazily so this module also loads in demo mode.
"""

from __future__ import annotations

import re
import time

from .llm import invoke_llm_with_retry


# ==========================================================================
# Confidence heuristics — every analyst node below previously returned no
# confidence figure at all, so runner.py's stage "meta" never carried a
# "confidence" key and every agent card in the UI showed a hardcoded 0%
# (not a real "the model is uncertain" reading -- just a missing field).
# These are deliberately simple, data-completeness-based scores (how much
# of the real underlying data actually came back non-empty/non-error) --
# an honest "how much did I actually have to work with" signal, not a
# model-reported certainty, so it stays consistent across LLM providers.
# ==========================================================================
def _field_completeness_confidence(fields: dict, floor: float = 0.05, cap: float = 0.95) -> float:
    """Fraction of `fields` that hold a real (non-missing, non-error)
    value. Used for fundamentals/market, where each field is one metric
    or indicator that's either a real number/string or an "N/A"/"Error"
    placeholder."""
    fields = {k: v for k, v in fields.items() if not str(k).startswith("_")}
    if not fields:
        return 0.0
    good = 0
    for v in fields.values():
        if v is None:
            continue
        s = str(v).strip()
        if not s or s.upper() in {"N/A", "NA", "NONE", "NULL"} or s.lower().startswith("error"):
            continue
        good += 1
    if good == 0:
        return 0.0
    return round(min(max(good / len(fields), floor), cap), 2)


def _text_confidence(text: str, target_chars: int, weight: float = 1.0) -> float:
    """Confidence contribution from one block of fetched text: 0 if it's
    an error placeholder or empty, otherwise scales up to `weight` as the
    block approaches `target_chars` (a rough "did we get a substantive
    amount of real content" proxy)."""
    text = (text or "").strip()
    if not text or text.lower().startswith("error"):
        return 0.0
    return weight * min(1.0, len(text) / max(target_chars, 1))


def extract_final_proposal(report_text: str) -> str:
    """Pulls the FINAL TRANSACTION PROPOSAL verdict out of a report so it
    survives truncation elsewhere (reports get sliced to a few hundred chars
    when threaded into later prompts). Searches a window of text after the
    anchor phrase rather than matching same-line only, since the LLM
    sometimes puts the verdict on the next line
    ("FINAL TRANSACTION PROPOSAL:**\\n**SELL** - ...").
    """
    report_text = str(report_text)
    idx = report_text.upper().find("FINAL TRANSACTION PROPOSAL")
    if idx == -1:
        return ""
    window = report_text[idx: idx + 150]
    m = re.search(r"\b(BUY|SELL|HOLD)\b", window, re.IGNORECASE)
    if not m:
        return ""
    return f"FINAL TRANSACTION PROPOSAL: {m.group(1).upper()}"


def _ta_utils(ticker: str = ""):
    """Grab the data-fetching + instrument-context helpers the agents need
    (lazy import).

    ✅ CHANGED: get_fundamentals/get_balance_sheet/get_cashflow/
    get_income_statement/get_stock_data/get_indicators/get_news/
    get_global_news now come from `.data_providers` (FMP + Finnhub) instead
    of tradingagents' yfinance-backed tools — output format is unchanged, so
    everything downstream in this file still works as-is.
    build_instrument_context/get_language_instruction are unrelated to the
    data-source swap and stay on the real (non-black-box) tradingagents
    implementation.

    ✅ CHANGED (DSE): when `ticker` is a live Dhaka Stock Exchange trading
    code (checked via symbol_utils.is_dse_ticker, which consults bdshare's
    real trading-code list), the data-fetching functions instead come from
    tradingagents.agents.utils.agent_utils — the original, non-FMP toolset,
    which routes through interface.py's route_to_vendor() and auto-selects
    the "dse" vendor (bdshare-backed) for these tickers. Default ticker=""
    preserves the old FMP/Finnhub behavior for every call site that doesn't
    pass one — those only use build_instrument_context/get_language_
    instruction, which are unaffected either way.
    """
    from tradingagents.agents.utils.agent_utils import (
        build_instrument_context,
        get_language_instruction,
    )
    from tradingagents.dataflows.symbol_utils import is_dse_ticker

    if ticker and is_dse_ticker(ticker):
        from tradingagents.agents.utils.agent_utils import (
            get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement,
            get_stock_data, get_indicators,
            get_news, get_global_news,
        )
    else:
        from .data_providers import (
            get_fundamentals, get_balance_sheet, get_cashflow, get_income_statement,
            get_stock_data, get_indicators,
            get_news, get_global_news,
        )
    return {
        "build_instrument_context": build_instrument_context,
        "get_language_instruction": get_language_instruction,
        "get_fundamentals": get_fundamentals,
        "get_balance_sheet": get_balance_sheet,
        "get_cashflow": get_cashflow,
        "get_income_statement": get_income_statement,
        "get_stock_data": get_stock_data,
        "get_indicators": get_indicators,
        "get_news": get_news,
        "get_global_news": get_global_news,
    }


# ==========================================================================
# Analyst team
# ==========================================================================
def create_fundamentals_analyst(llm, log=print):
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

    def node(state):
        current_date = state["trade_date"]
        company = state["company_of_interest"]
        U = _ta_utils(company)
        instrument_context = U["build_instrument_context"](company)
        log(f"Fetching fundamentals for {company} on {current_date}")

        from tradingagents.dataflows.symbol_utils import is_dse_ticker
        _is_dse = is_dse_ticker(company)
        # 🔴 FIXED (reverted): a previous version of this set freq="annual"
        # for DSE tickers, reasoning that dse_statement_extractor.py was
        # built around annual-report PDFs. But this report's own field
        # names (net_income_q, gross_profit_q, ...) and section label
        # ("MOST RECENT QUARTER") were designed for QUARTERLY data --
        # confirmed as the right call now that a real quarterly (Q1 2026
        # un-audited) PDF is actually in use for this ticker. freq only
        # controls which dict key the extracted data is wrapped under
        # ("quarterlyReports" vs "annualReports") -- it doesn't change
        # what get extracted -- so this now correctly matches what's
        # really in the PDF instead of mislabeling quarterly figures as
        # annual. Whichever type of PDF you actually place on disk for a
        # ticker, request the freq that matches it.
        _stmt_freq = "quarterly"

        tool_results = {}
        for tool_name, tool_fn, args in [
            ("get_fundamentals", U["get_fundamentals"], {"ticker": company, "curr_date": current_date}),
            ("get_balance_sheet", U["get_balance_sheet"],
             {"ticker": company, "freq": _stmt_freq, "curr_date": current_date}),
            ("get_cashflow", U["get_cashflow"],
             {"ticker": company, "freq": _stmt_freq, "curr_date": current_date}),
            ("get_income_statement", U["get_income_statement"],
             {"ticker": company, "freq": _stmt_freq, "curr_date": current_date}),
        ]:
            log(f"calling {tool_name}")
            try:
                tool_results[tool_name] = str(tool_fn.invoke(args))[:3000]
            except Exception as e:  # noqa: BLE001
                tool_results[tool_name] = f"Error fetching {tool_name}: {e}"
                log(f"  error {tool_name}: {e}")

        def extract_numbers(raw, keys):
            results = {}
            for key in keys:
                for line in raw.split("\n"):
                    if key.lower() in line.lower():
                        nums = re.findall(r"-?\d+\.?\d*e?[+-]?\d*", line)
                        nums = [float(n) for n in nums if abs(float(n)) > 1000]
                        if nums:
                            results[key] = nums[0]
                            break
            return results

        def extract_dict_numbers(raw, keys):
            """dse_statement_extractor.get_statement() returns a Python dict,
            which `str(tool_fn.invoke(args))` turns into a *single-line* repr
            (no newlines) -- unlike yfinance's DataFrame str() output, which
            is naturally one row per line. extract_numbers() above scans
            "per line" and grabs whichever large number appears first on that
            line; on a single-line dict repr that means every key would
            silently resolve to the SAME number instead of honestly showing
            N/A. Anchor directly on `'key': value` so each key only ever
            matches its own value."""
            results = {}
            for key in keys:
                m = re.search(rf"['\"]{re.escape(key)}['\"]\s*:\s*(-?[\d.]+)", raw)
                if m:
                    try:
                        results[key] = float(m.group(1))
                    except ValueError:
                        continue
            return results

        def fmt(n):
            try:
                n = float(n)
                if abs(n) >= 1e9:
                    return f"${n / 1e9:.2f}B"
                if abs(n) >= 1e6:
                    return f"${n / 1e6:.1f}M"
                return f"${n:,.0f}"
            except Exception:  # noqa: BLE001
                return str(n)

        fund = tool_results["get_fundamentals"]
        inc = tool_results["get_income_statement"]
        cf = tool_results["get_cashflow"]
        bs = tool_results["get_balance_sheet"]

        def g(pattern, raw):
            m = re.search(pattern, raw)
            return m.group(1) if m else "N/A"

        if _is_dse:
            # ✅ FIXED: dsebd.org's snapshot (dse_fundamentals.py) and the
            # PDF-extracted statements (dse_statement_extractor.py) use their
            # own label/key conventions, not yfinance/Alpha Vantage's. The
            # fixed regex patterns in the `else` branch below (e.g. "PE Ratio",
            # "Market Cap", "Total Revenue") never matched DSE output, so
            # every field silently fell back to "N/A" for BD tickers. This
            # branch parses the actual DSE formats instead of assuming a
            # US-vendor shape.

            def g_dse(keywords, raw, exclude=()):
                """Scan the DSE snapshot's `Label: Value` lines for a keyword
                substring (mirrors the same keyword-matching dse_fundamentals.py
                itself uses to pick fields off dsebd.org, since dsebd.org's
                exact label wording isn't guaranteed / can drift) and pull the
                first number out of that line."""
                for line in raw.split("\n"):
                    low = line.lower()
                    if any(k in low for k in keywords) and not any(e in low for e in exclude):
                        m = re.search(r"(-?[\d,]+\.?\d*)", line.split(":", 1)[-1])
                        if m:
                            return m.group(1).replace(",", "")
                return "N/A"

            pe_val = g_dse(["pe(x)", "p/e"], fund)
            eps_val = g_dse(["eps"], fund, exclude=("change", "p/e", "ratio"))
            mcap_val = g_dse(["market capitalization", "market cap"], fund)
            div_val = g_dse(["dividend"], fund)
            # ✅ CHANGED: dsebd.org's page doesn't publish a computed
            # dividend *yield* (dividend / current price) -- the "dividend"
            # line this matches is the last-declared cash dividend
            # percentage of FACE VALUE (e.g. "10%" on a 10-taka face value
            # share), a fundamentally different, usually much larger number
            # than a true yield. Labeling it "Dividend Yield" in the report
            # asserts a calculation that was never actually done.
            div_label = "Last Declared Dividend (% of face value, not a computed yield)"
            # 🔴 FIXED: rev_val used to stay hardcoded "N/A" for DSE tickers
            # unconditionally -- true for the dsebd.org snapshot page (which
            # really doesn't publish it), but WRONG once a statement PDF is
            # on disk: totalRevenue is a real field in the DSE extractor's
            # income-statement schema (confirmed against a real quarterly
            # filing, BATBC Q1 2026 -- "Net revenue from contracts with
            # customers"). Placeholder here; overwritten below once
            # inc_rows is available, same pattern as net_income_val etc.
            rev_val = "N/A"
            beta_val = "N/A"
            hi52_val = "N/A"
            lo52_val = "N/A"
            # ✅ CHANGED: 50-Day SMA WAS being hardcoded N/A here even though
            # it's not actually a dsebd.org-snapshot-only field -- it's a
            # price-derived technical indicator, and get_indicators (the
            # same tool the Market Analyst already calls, computed from
            # bdshare OHLCV history) can provide it directly rather than
            # requiring dsebd.org to publish it.
            try:
                sma_raw = str(U["get_indicators"].invoke({
                    "symbol": company, "indicator": "close_50_sma", "curr_date": current_date,
                }))
                m_sma = re.search(r"(-?[\d,]+\.?\d*)", sma_raw)
                sma50_val = m_sma.group(1).replace(",", "") if m_sma else "N/A"
            except Exception:  # noqa: BLE001
                sma50_val = "N/A"

            # dse_statement_extractor.py returns an Alpha-Vantage-*shaped*
            # dict but with its own camelCase keys (see STATEMENT_SCHEMAS) --
            # "Total Revenue" etc. never existed in that JSON, so
            # extract_numbers was searching for the wrong keys entirely.
            # Net Debt / Free Cash Flow aren't literal fields in the DSE
            # schema at all, so derive them from the fields that are
            # (long+short term debt; operating cash flow minus capex).
            inc_rows = extract_dict_numbers(inc, ["totalRevenue", "grossProfit", "operatingIncome",
                                                  "netIncome", "ebitda"])
            cf_rows = extract_dict_numbers(cf, ["operatingCashflow", "capitalExpenditures"])
            bs_rows = extract_dict_numbers(bs, ["longTermDebt", "shortTermDebt", "cashAndCashEquivalents"])

            # Now that inc_rows exists, use it for revenue if the statement
            # PDF actually had a figure -- otherwise rev_val stays "N/A"
            # (still true when there's no PDF on disk at all).
            if "totalRevenue" in inc_rows:
                rev_val = fmt(inc_rows["totalRevenue"])

            net_income_val = fmt(inc_rows.get("netIncome", "N/A"))
            gross_profit_val = fmt(inc_rows.get("grossProfit", "N/A"))
            operating_income_val = fmt(inc_rows.get("operatingIncome", "N/A"))
            ebitda_val = fmt(inc_rows.get("ebitda", "N/A"))

            total_debt_num = None
            if "longTermDebt" in bs_rows or "shortTermDebt" in bs_rows:
                total_debt_num = bs_rows.get("longTermDebt", 0.0) + bs_rows.get("shortTermDebt", 0.0)
            net_debt_num = (
                total_debt_num - bs_rows["cashAndCashEquivalents"]
                if total_debt_num is not None and "cashAndCashEquivalents" in bs_rows
                else None
            )
            fcf_num = (
                cf_rows["operatingCashflow"] - cf_rows["capitalExpenditures"]
                if "operatingCashflow" in cf_rows and "capitalExpenditures" in cf_rows
                else None
            )
            free_cash_flow_val = fmt(fcf_num) if fcf_num is not None else "N/A"
            buybacks_val = "N/A"  # not a field the DSE schema exposes
            net_debt_val = fmt(net_debt_num) if net_debt_num is not None else "N/A"
            total_debt_val = fmt(total_debt_num) if total_debt_num is not None else "N/A"
        else:
            pe_val = g(r"PE Ratio.*?:\s*([\d.]+)", fund)
            eps_val = g(r"EPS \(TTM\).*?:\s*([\d.]+)", fund)
            mcap = re.search(r"Market Cap.*?:\s*([\d.]+)", fund)
            rev_ttm = re.search(r"Revenue \(TTM\).*?:\s*([\d.]+)", fund)
            mcap_val = fmt(mcap.group(1)) if mcap else "N/A"
            rev_val = fmt(rev_ttm.group(1)) if rev_ttm else "N/A"
            beta_val = g(r"Beta.*?:\s*([\d.]+)", fund)
            div_val = g(r"Dividend Yield.*?:\s*([\d.]+)", fund)
            div_label = "Dividend Yield"
            hi52_val = g(r"52 Week High.*?:\s*([\d.]+)", fund)
            lo52_val = g(r"52 Week Low.*?:\s*([\d.]+)", fund)
            sma50_val = g(r"50 Day Average.*?:\s*([\d.]+)", fund)

            inc_rows = extract_numbers(inc, ["Total Revenue", "Gross Profit", "Operating Income",
                                             "Net Income From Continuing", "Normalized EBITDA"])
            cf_rows = extract_numbers(cf, ["Free Cash Flow", "Repurchase Of Capital Stock"])
            bs_rows = extract_numbers(bs, ["Net Debt", "Total Debt", "Cash And Cash Equivalents"])

            net_income_val = fmt(inc_rows.get("Net Income From Continuing", "N/A"))
            gross_profit_val = fmt(inc_rows.get("Gross Profit", "N/A"))
            operating_income_val = fmt(inc_rows.get("Operating Income", "N/A"))
            ebitda_val = fmt(inc_rows.get("Normalized EBITDA", "N/A"))
            free_cash_flow_val = fmt(cf_rows.get("Free Cash Flow", "N/A"))
            buybacks_val = fmt(cf_rows.get("Repurchase Of Capital Stock", "N/A"))
            net_debt_val = fmt(bs_rows.get("Net Debt", "N/A"))
            total_debt_val = fmt(bs_rows.get("Total Debt", "N/A"))

        # ✅ CHANGED (per explicit request): for DSE tickers, Beta and Stock
        # Buybacks aren't just "not fetched yet" -- they're concepts DSE-
        # listed companies' disclosures don't report at all (no beta
        # calculation is published anywhere on dsebd.org, and share
        # buybacks aren't standard practice/reporting line item for
        # Bangladeshi listed companies the way US 10-Q "Repurchase Of
        # Capital Stock" is). Showing them as permanent "N/A" rows made
        # the report look more incomplete than it really is and risked
        # nudging the LLM toward extra caution over fields that were never
        # going to have data. Omitted entirely for DSE tickers rather than
        # displayed empty; kept for the non-DSE (yfinance/FMP) path where
        # they're genuine, normally-populated fields.
        if _is_dse:
            data_summary = f"""
COMPANY: {company} | DATE: {current_date}

MARKET DATA:
- Market Cap: {mcap_val}
- P/E Ratio: {pe_val}
- EPS: {eps_val}
- Revenue: {rev_val}
- {div_label}: {div_val}%
- 50-Day SMA: {sma50_val}

MOST RECENT QUARTER (income statement):
- Net Income: {net_income_val}
- Gross Profit: {gross_profit_val}
- Operating Income: {operating_income_val}
- EBITDA: {ebitda_val}

CASH FLOW (most recent quarter):
- Free Cash Flow: {free_cash_flow_val}

BALANCE SHEET (most recent quarter):
- Net Debt: {net_debt_val}
- Total Debt: {total_debt_val}
"""
        else:
            data_summary = f"""
COMPANY: {company} | DATE: {current_date}

MARKET DATA (TTM):
- Market Cap: {mcap_val}
- P/E Ratio: {pe_val}
- EPS (TTM): {eps_val}
- Revenue (TTM): {rev_val}
- Beta: {beta_val}
- {div_label}: {div_val}%
- 52-Week Range: {lo52_val} - {hi52_val}
- 50-Day SMA: {sma50_val}

MOST RECENT QUARTER (income statement):
- Net Income: {net_income_val}
- Gross Profit: {gross_profit_val}
- Operating Income: {operating_income_val}
- EBITDA: {ebitda_val}

CASH FLOW (most recent quarter):
- Free Cash Flow: {free_cash_flow_val}
- Stock Buybacks: {buybacks_val}

BALANCE SHEET (most recent quarter):
- Net Debt: {net_debt_val}
- Total Debt: {total_debt_val}
"""

        prompt = f"""You are a senior financial analyst. Today is {current_date}.

Write a professional fundamental analysis report for {company} using ONLY the data below.
Structure: Company Overview -> Profitability -> Balance Sheet -> Cash Flow -> Risks -> Outlook
End with a Markdown table and: FINAL TRANSACTION PROPOSAL: **BUY** / **HOLD** / **SELL**

RULES:
- Use ONLY the numbers below. Do NOT invent any figures.
- If a metric shows N/A, say "data not available".
- Missing/N/A fields are a normal, common limitation -- by themselves they
  are NOT a reason to default to HOLD. Base your verdict on what the
  available numbers actually show. If the core figures you DO have (P/E,
  EPS, revenue, profitability, debt levels) clearly point one direction,
  give a decisive BUY or SELL and say plainly which data points you
  couldn't factor in and why that doesn't change the call.
- Reserve HOLD for when the available data is itself genuinely mixed or
  conflicting (e.g. strong profitability but rising debt, or a cheap P/E
  alongside deteriorating cash flow) -- not merely incomplete. "I don't
  have every field" is not a basis for HOLD on its own.

{data_summary}
""" + U["get_language_instruction"]()

        messages = [
            SystemMessage(content="You are a financial analyst. Use ONLY the provided numbers. Never invent data."),
            HumanMessage(content=prompt),
        ]
        report = invoke_llm_with_retry(llm, messages).content
        log("fundamentals report ready")

        fund_metrics = {
            "market_cap": mcap_val, "pe_ratio": pe_val, "eps_ttm": eps_val,
            "revenue_ttm": rev_val, "dividend_yield": div_val,
            "50d_sma": sma50_val,
            "net_income_q": net_income_val,
            "gross_profit_q": gross_profit_val,
            "operating_income_q": operating_income_val,
            "free_cash_flow_q": free_cash_flow_val,
            "net_debt": net_debt_val,
            "total_debt": total_debt_val,
        }
        # ✅ CHANGED (per explicit request): beta / 52-week high-low / EBITDA
        # dropped for DSE tickers only -- beta and 52-week range are never
        # populated at all for DSE (not published on the dsebd.org snapshot
        # page, set to "N/A" unconditionally in the DSE branch above), and
        # ebitda_q depends on an LLM-inferred figure from the statement PDF
        # that isn't reliable enough to show as a headline metric. Non-DSE
        # (yfinance-backed) tickers keep all four -- those come from real
        # market data and are worth showing.
        if not _is_dse:
            fund_metrics["beta"] = beta_val
            fund_metrics["52w_high"] = hi52_val
            fund_metrics["52w_low"] = lo52_val
            fund_metrics["ebitda_q"] = ebitda_val
        # 🔧 TEMP DEBUG: surfaces what get_fundamentals actually returned,
        # right in the same "metrics" panel you already screenshot -- no
        # need to dig through Railway logs. If everything above is N/A,
        # this field tells us why in one look:
        #   - starts with "DSE fundamentals unavailable for..." -> the
        #     dsebd.org request itself failed (network/cert/blocked)
        #   - starts with "No fundamentals table found for..." -> the page
        #     loaded but didn't parse into label:value rows (structure
        #     changed, or dsebd.org served something other than the real
        #     company page, e.g. a block/interstitial page)
        #   - starts with "Error fetching get_fundamentals:" -> the tool
        #     call itself raised an exception
        #   - starts with "DSE fundamentals snapshot --" and has PE(x)/EPS/
        #     Market Capitalization lines -> the fetch worked fine and the
        #     issue is elsewhere (label wording g_dse doesn't recognize)
        # Remove this key once the real cause is confirmed and fixed.
        fund_confidence = _field_completeness_confidence(fund_metrics)
        fund_metrics["_debug_raw_fundamentals"] = str(fund)[:250]
        if _is_dse:
            fund_metrics["_debug_raw_balance_sheet"] = str(bs)[:250]
        return {"fundamentals_report": report, "fund_metrics": fund_metrics,
                "fundamentals_confidence": fund_confidence}

    return node


def create_market_analyst(llm, indicators_list, log=print):
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from datetime import datetime, timedelta

    def node(state):
        current_date = state["trade_date"]
        company = state["company_of_interest"]
        U = _ta_utils(company)
        asset_type = state.get("asset_type", "stock")
        instrument_context = U["build_instrument_context"](company, asset_type)
        log(f"Fetching market data for {company} on {current_date}")

        end_dt = datetime.strptime(current_date, "%Y-%m-%d")
        start_date = (end_dt - timedelta(days=30)).strftime("%Y-%m-%d")

        log("calling get_stock_data")
        try:
            stock_data = str(U["get_stock_data"].invoke({
                "symbol": company, "start_date": start_date, "end_date": current_date,
            }))[:2000]
        except Exception as e:  # noqa: BLE001
            stock_data = f"Error: {e}"

        log("calling get_indicators")
        ind_parts = []
        for ind_name in indicators_list:
            try:
                val = U["get_indicators"].invoke({
                    "symbol": company, "indicator": ind_name, "curr_date": current_date,
                })
                ind_parts.append(f"{ind_name}: {str(val)[:300]}")
            except Exception as ie:  # noqa: BLE001
                ind_parts.append(f"{ind_name}: Error - {str(ie)[:100]}")
        indicators_str = "\n".join(ind_parts)

        def _extract(raw_str):
            for line in raw_str.split("\n"):
                line = line.strip()
                if re.match(r"\d{4}-\d{2}-\d{2}:", line) and "N/A" not in line:
                    m = re.search(r":\s*(-?\d+\.?\d+)", line)
                    if m:
                        return float(m.group(1))
            return None

        indicators_dict = {}
        for item in ind_parts:
            if ": " in item:
                k, _, v = item.partition(": ")
                val = _extract(v)
                indicators_dict[k.strip()] = val if val is not None else v.strip()[:100]

        prompt = f"""You are a trading analyst. Today is {current_date}.
{instrument_context}

Using the REAL data below, write a brief technical analysis report for {company}.
Include RSI, MACD, Bollinger Bands, SMA analysis.

At the very end, output a Markdown table with EXACTLY these columns:
| Indicator | Value | Signal | Interpretation |

=== STOCK PRICE DATA ===
{stock_data}

=== TECHNICAL INDICATORS ===
{indicators_str}
""" + U["get_language_instruction"]()

        messages = [
            SystemMessage(content="You are a senior trading analyst. Write reports based only on provided data. Always end with the required Markdown table."),
            HumanMessage(content=prompt),
        ]
        report = invoke_llm_with_retry(llm, messages).content
        log("market report ready")

        return {
            "market_report": report,
            "indicators_parsed": indicators_dict,
            "market_raw_data": {"stock_data": stock_data, "indicators": indicators_dict},
            "market_confidence": _field_completeness_confidence(indicators_dict),
        }

    return node


def create_news_analyst(llm, log=print):
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from datetime import datetime, timedelta

    def node(state):
        current_date = state["trade_date"]
        company = state["company_of_interest"]
        U = _ta_utils(company)
        asset_type = state.get("asset_type", "stock")
        instrument_context = U["build_instrument_context"](company, asset_type)
        log(f"Fetching news for {company} on {current_date}")

        log("calling get_news")
        try:
            end_dt = datetime.strptime(current_date, "%Y-%m-%d")
            start_dt = end_dt - timedelta(days=7)
            company_news = str(U["get_news"].invoke({
                "ticker": company, "start_date": start_dt.strftime("%Y-%m-%d"),
                "end_date": current_date,
            }))[:3000]
        except Exception as e:  # noqa: BLE001
            company_news = f"Error: {e}"

        log("calling get_global_news")
        try:
            global_news = str(U["get_global_news"].invoke({"curr_date": current_date}))[:2000]
        except Exception as e:  # noqa: BLE001
            global_news = f"Error: {e}"

        prompt = f"""You are a news analyst. Today is {current_date}.
{instrument_context}

Using the REAL news data below, write a brief news analysis report for {company}.
Sections: Company News Summary -> Global Macro Trends -> Sentiment Assessment -> Key Risks

At the very end, output a Markdown table with EXACTLY these 5 columns:
| Category | Headline | Sentiment | Impact | Source |
(Fill 4-6 rows. Sentiment must be POSITIVE / NEGATIVE / NEUTRAL.)

=== COMPANY NEWS ({company}) ===
{company_news}

=== GLOBAL MARKET NEWS ===
{global_news}
""" + U["get_language_instruction"]()

        messages = [
            SystemMessage(content="You are a senior news analyst. Write reports based only on provided data. Always end with the required Markdown table."),
            HumanMessage(content=prompt),
        ]
        report = invoke_llm_with_retry(llm, messages).content
        log("news report ready")

        sentiments = re.findall(r"\|\s*\w.*?\|\s*(POSITIVE|NEGATIVE|NEUTRAL)\s*\|", report, re.IGNORECASE)
        pos = sum(1 for s in sentiments if "POSITIVE" in s.upper())
        neg = sum(1 for s in sentiments if "NEGATIVE" in s.upper())
        neu = sum(1 for s in sentiments if "NEUTRAL" in s.upper())
        overall_m = re.search(r"(POSITIVE|NEGATIVE|NEUTRAL|BULLISH|BEARISH)", report, re.IGNORECASE)
        overall = overall_m.group(1).upper() if overall_m else "NEUTRAL"
        tbl_m = re.search(r"(\|.*?Category.*?\|.*?(?:\n\|[-| ]+\|)(?:\n\|.*?\|)+)", report, re.IGNORECASE | re.DOTALL)

        news_metrics = {
            "positive_count": pos, "negative_count": neg, "neutral_count": neu,
            "overall_sentiment": overall,
            "company_news_chars": len(company_news), "global_news_chars": len(global_news),
        }
        # Company news carries most of the weight -- it's what the report is
        # actually about; global news is background context.
        news_confidence = round(min(0.95,
            _text_confidence(company_news, target_chars=1200, weight=0.75)
            + _text_confidence(global_news, target_chars=800, weight=0.25)), 2)
        return {
            "news_report": report, "news_metrics": news_metrics,
            "news_table_md": tbl_m.group(1) if tbl_m else "",
            "news_raw": {"company_news": company_news, "global_news": global_news},
            "news_confidence": news_confidence,
        }

    return node


def create_sentiment_analyst(llm, log=print):
    """Runs right after the News Analyst in the pipeline (see runner.py), so
    state["news_metrics"] / state["news_table_md"] are already populated
    with real, per-headline POSITIVE/NEGATIVE/NEUTRAL tags -- for DSE
    tickers, sourced from dsebd.org corporate disclosures + sharenews24.com
    market news (see dse_news.py); for everything else, Yahoo Finance.

    This is now the primary sentiment signal. StockTwits/Reddit have zero
    DSE coverage, and Finnhub's /news-sentiment endpoint needs a paid plan
    and doesn't cover DSE names either way -- so rather than call dead/
    always-empty tools and fall back to "no data", this reuses the News
    Analyst's own structured breakdown directly. It's honestly framed as
    news-flow sentiment (what's being reported), not measured market
    sentiment (price/volume-derived crowd positioning) -- the Data Source
    Review section below says so explicitly."""
    from langchain_core.messages import HumanMessage, SystemMessage
    U = _ta_utils()

    def node(state):
        current_date = state["trade_date"]
        company = state["company_of_interest"]
        log(f"Fetching sentiment for {company} on {current_date}")

        news_metrics = state.get("news_metrics", {}) or {}
        news_table = str(state.get("news_table_md", "") or "").strip()
        news_report = str(state.get("news_report", ""))[:1500]

        if news_table:
            log(f"using News Analyst's headline table: "
                f"{news_metrics.get('positive_count', 0)} positive / "
                f"{news_metrics.get('negative_count', 0)} negative / "
                f"{news_metrics.get('neutral_count', 0)} neutral")
            data_sections = f"""Positive headlines: {news_metrics.get("positive_count", 0)}
Negative headlines: {news_metrics.get("negative_count", 0)}
Neutral headlines:  {news_metrics.get("neutral_count", 0)}
News Analyst's overall read: {news_metrics.get("overall_sentiment", "N/A")}

Per-headline breakdown (tagged moments ago by the News Analyst from real scraped articles):
{news_table}"""
        else:
            log("no news headline table available -- falling back to narrative inference")
            data_sections = "No structured news-sentiment breakdown available. Infer from the news report narrative below."

        prompt = f"""You are a sentiment analyst. Today is {current_date}.
IMPORTANT: Base your analysis ONLY on the data below. Do NOT invent scores.

No social-sentiment API (StockTwits, Reddit, Finnhub) has usable coverage for {company} --
StockTwits/Reddit carry essentially no DSE-listed discussion, and Finnhub's sentiment
endpoint requires a paid plan and doesn't cover DSE names anyway. Your sole grounded input
is therefore the News Analyst's per-headline sentiment breakdown below. This reflects
news-flow sentiment (what's being reported about the company), not measured market
sentiment (price/volume-derived crowd positioning) -- state this distinction explicitly
in your Data Source Review.

Analyze market sentiment for {company}.
Sections: Data Source Review -> Score Breakdown -> Key Signals -> Confidence Assessment

At the very end, output a Markdown table with EXACTLY these columns:
| Source | Sentiment | Score (1-10) | Confidence | Key Signal |

=== NEWS-FLOW SENTIMENT (from News Analyst) ===
{data_sections}

=== NEWS REPORT NARRATIVE ===
{news_report}
""" + U["get_language_instruction"]()

        messages = [
            SystemMessage(content="You are a senior sentiment analyst. Be specific about data sources. Always end with the required Markdown table."),
            HumanMessage(content=prompt),
        ]
        report = invoke_llm_with_retry(llm, messages).content
        log("sentiment report ready")

        score_m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", report)
        conf_m = re.search(r"(High|Medium|Low)\s*[Cc]onfidence", report)
        overall_m = re.search(r"(BULLISH|BEARISH|NEUTRAL|POSITIVE|NEGATIVE)", report, re.IGNORECASE)
        sentiment_metrics = {
            "score": score_m.group(1) if score_m else "N/A",
            "confidence": conf_m.group(1) if conf_m else "N/A",
            "overall": overall_m.group(1).upper() if overall_m else "NEUTRAL",
        }
        # Numeric confidence (used by the agent-card UI, separate from the
        # High/Medium/Low label above): starts from whether a real
        # structured headline breakdown was available at all, then nudged
        # by the LLM's own stated confidence label if it gave one.
        n_tagged = (news_metrics.get("positive_count", 0) + news_metrics.get("negative_count", 0)
                    + news_metrics.get("neutral_count", 0))
        base = 0.65 if news_table else 0.2
        if news_table:
            base = min(0.9, base + 0.03 * min(n_tagged, 8))
        label = (conf_m.group(1).lower() if conf_m else "")
        nudge = {"high": 0.15, "medium": 0.0, "low": -0.2}.get(label, 0.0)
        sentiment_confidence = round(min(max(base + nudge, 0.05), 0.95), 2)
        return {"sentiment_report": report, "sentiment_metrics": sentiment_metrics,
                "sentiment_confidence": sentiment_confidence}

    return node


# ==========================================================================
# Investment debate (bull / bear / facilitator)
# ==========================================================================
def _reports(state):
    return (
        str(state["market_report"])[:500], str(state["sentiment_report"])[:500],
        str(state["news_report"])[:500], str(state["fundamentals_report"])[:500],
    )


def create_bull_researcher(llm):
    U = _ta_utils()

    def node(state):
        ds = state["investment_debate_state"]
        market, sentiment, news, fundamentals = _reports(state)
        prompt = f"""IMPORTANT: Use ONLY the data in the reports below. Do NOT invent facts or figures.
You are a Bull Analyst advocating for investing in the stock.
Market report: {market}
Sentiment report: {sentiment}
News report: {news}
Fundamentals report: {fundamentals}
Debate history: {ds.get('history', '')}
Last bear argument: {ds.get('current_response', '')}
Present a compelling bull argument with specific growth opportunities and strengths.
""" + U["get_language_instruction"]()
        argument = f"Bull Analyst: {invoke_llm_with_retry(llm, prompt).content}"
        return {"investment_debate_state": {
            "history": ds.get("history", "") + "\n" + argument,
            "bull_history": ds.get("bull_history", "") + "\n" + argument,
            "bear_history": ds.get("bear_history", ""),
            "current_response": argument,
            "count": ds["count"] + 1,
        }}

    return node


def create_bear_researcher(llm):
    U = _ta_utils()

    def node(state):
        ds = state["investment_debate_state"]
        market, sentiment, news, fundamentals = _reports(state)
        prompt = f"""IMPORTANT: Use ONLY the data in the reports below. Do NOT invent facts or figures.
You are a Bear Analyst making the case against investing in the stock.
Market report: {market}
Sentiment report: {sentiment}
News report: {news}
Fundamentals report: {fundamentals}
Debate history: {ds.get('history', '')}
Last bull argument: {ds.get('current_response', '')}
Present a compelling bear argument with specific risks and weaknesses.
""" + U["get_language_instruction"]()
        argument = f"Bear Analyst: {invoke_llm_with_retry(llm, prompt).content}"
        return {"investment_debate_state": {
            "history": ds.get("history", "") + "\n" + argument,
            "bear_history": ds.get("bear_history", "") + "\n" + argument,
            "bull_history": ds.get("bull_history", ""),
            "current_response": argument,
            "count": ds["count"] + 1,
        }}

    return node


def create_investment_facilitator(llm):
    U = _ta_utils()

    def node(state):
        ds = state["investment_debate_state"]
        prompt = f"""IMPORTANT: Base your evaluation ONLY on the debate history provided below. Do NOT add external knowledge.
You are the Investment Debate Facilitator. Your job is to:
1. Review the full debate between Bull and Bear analysts
2. Objectively evaluate which side presented stronger evidence
3. Declare a WINNER with clear reasoning
4. Provide a final investment recommendation

Full Debate History:
{ds.get('history', '')}

Total arguments made: {ds.get('count', 0)}

Declare: BULL WINS / BEAR WINS / DRAW
Then give your final recommendation: BUY / SELL / HOLD with confidence level (High/Medium/Low).
""" + U["get_language_instruction"]()
        decision = invoke_llm_with_retry(llm, prompt).content
        return {"investment_facilitator_decision": decision,
                "investment_debate_state": {**ds, "facilitator_decision": decision}}

    return node


# ==========================================================================
# Trader (structured)
# ==========================================================================
def create_trader(llm):
    from tradingagents.agents.schemas import TraderProposal, render_trader_proposal
    from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
    from tradingagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext

    structured_llm = bind_structured(llm, TraderProposal, "Trader")

    def node(state):
        company_name = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(company_name, asset_type)
        investment_plan = state["investment_plan"]

        messages = [
            {"role": "system", "content": (
                "You are a trading agent analyzing market data to make investment decisions. "
                "Based on your analysis, provide a specific recommendation to buy, sell, or hold. "
                "Anchor your reasoning in the analysts' reports and the research plan."
                + get_language_instruction())},
            {"role": "user", "content": (
                f"Based on a comprehensive analysis by a team of analysts, here is an investment "
                f"plan tailored for {company_name}. {instrument_context} This plan incorporates "
                f"insights from current technical market trends, macroeconomic indicators, and "
                f"social media sentiment. Use this plan as a foundation for evaluating your next "
                f"trading decision.\n\nProposed Investment Plan: {investment_plan}\n\n"
                f"Leverage these insights to make an informed and strategic decision.")},
        ]

        trader_plan = None
        for attempt in range(3):
            try:
                trader_plan = invoke_structured_or_freetext(
                    structured_llm, llm, messages, render_trader_proposal, "Trader")
                break
            except Exception as e:  # noqa: BLE001
                if "429" in str(e) or "rate_limit" in str(e).lower():
                    time.sleep(60 * (attempt + 1))
                else:
                    raise
        return {"trader_investment_plan": trader_plan, "sender": "Trader"}

    return node


# ==========================================================================
# Risk debate (aggressive / conservative / neutral / facilitator)
# ==========================================================================
def _risk_reports(state):
    return (
        str(state["market_report"])[:500], str(state["sentiment_report"])[:500],
        str(state["news_report"])[:500], str(state["fundamentals_report"])[:500],
        str(state["trader_investment_plan"])[:500],
    )


def create_aggressive_debator(llm):
    U = _ta_utils()

    def node(state):
        rd = state["risk_debate_state"]
        market, sentiment, news, fundamentals, trader = _risk_reports(state)
        prompt = f"""IMPORTANT: Use ONLY the analyst reports provided. Do NOT invent figures.
As the Aggressive Risk Analyst, champion high-reward opportunities.
Trader decision: {trader}
Market Report: {market}
Sentiment: {sentiment}
News: {news}
Fundamentals: {fundamentals}
History: {rd.get('history', '')}
Conservative argument: {rd.get('current_conservative_response', '')}
Neutral argument: {rd.get('current_neutral_response', '')}
Make a compelling case for high-risk high-reward approach. Speak conversationally.
""" + U["get_language_instruction"]()
        argument = f"Aggressive Analyst: {invoke_llm_with_retry(llm, prompt).content}"
        return {"risk_debate_state": {**rd,
            "history": rd.get("history", "") + "\n" + argument,
            "aggressive_history": rd.get("aggressive_history", "") + "\n" + argument,
            "latest_speaker": "Aggressive",
            "current_aggressive_response": argument,
            "count": rd["count"] + 1}}

    return node


def create_conservative_debator(llm):
    U = _ta_utils()

    def node(state):
        rd = state["risk_debate_state"]
        market, sentiment, news, fundamentals, trader = _risk_reports(state)
        prompt = f"""IMPORTANT: Use ONLY the analyst reports provided. Do NOT invent figures.
As the Conservative Risk Analyst, protect assets and minimize risk.
Trader decision: {trader}
Market Report: {market}
Sentiment: {sentiment}
News: {news}
Fundamentals: {fundamentals}
History: {rd.get('history', '')}
Aggressive argument: {rd.get('current_aggressive_response', '')}
Neutral argument: {rd.get('current_neutral_response', '')}
Make a compelling case for low-risk conservative approach. Speak conversationally.
""" + U["get_language_instruction"]()
        argument = f"Conservative Analyst: {invoke_llm_with_retry(llm, prompt).content}"
        return {"risk_debate_state": {**rd,
            "history": rd.get("history", "") + "\n" + argument,
            "conservative_history": rd.get("conservative_history", "") + "\n" + argument,
            "latest_speaker": "Conservative",
            "current_conservative_response": argument,
            "count": rd["count"] + 1}}

    return node


def create_neutral_debator(llm):
    U = _ta_utils()

    def node(state):
        rd = state["risk_debate_state"]
        market, sentiment, news, fundamentals, trader = _risk_reports(state)
        prompt = f"""IMPORTANT: Use ONLY the analyst reports provided. Do NOT invent figures.
As the Neutral Risk Analyst, provide a balanced perspective.
Trader decision: {trader}
Market Report: {market}
Sentiment: {sentiment}
News: {news}
Fundamentals: {fundamentals}
History: {rd.get('history', '')}
Aggressive argument: {rd.get('current_aggressive_response', '')}
Conservative argument: {rd.get('current_conservative_response', '')}
Provide a balanced moderate view. Speak conversationally.
""" + U["get_language_instruction"]()
        argument = f"Neutral Analyst: {invoke_llm_with_retry(llm, prompt).content}"
        return {"risk_debate_state": {**rd,
            "history": rd.get("history", "") + "\n" + argument,
            "neutral_history": rd.get("neutral_history", "") + "\n" + argument,
            "latest_speaker": "Neutral",
            "current_neutral_response": argument,
            "count": rd["count"] + 1}}

    return node


def create_risk_facilitator(llm):
    U = _ta_utils()

    def node(state):
        rd = state["risk_debate_state"]
        trader_decision = str(state.get("trader_investment_plan", ""))[:500]
        prompt = f"""IMPORTANT: Base your assessment ONLY on the debate history provided. Do NOT use external knowledge.
You are the Risk Management Debate Facilitator.

Trader's Original Decision: {trader_decision}

After {rd.get('count', 0)} total arguments across the rounds, evaluate the risk debate:

Aggressive Analyst Summary:
{rd.get('aggressive_history', '')[-800:]}

Conservative Analyst Summary:
{rd.get('conservative_history', '')[-800:]}

Neutral Analyst Summary:
{rd.get('neutral_history', '')[-800:]}

Your tasks:
1. Declare which risk perspective was most compelling: AGGRESSIVE / CONSERVATIVE / NEUTRAL
2. Synthesize a final risk assessment
3. Provide position sizing recommendation (e.g., 25% / 50% / 75% of portfolio)
4. Set stop-loss and take-profit levels based on the debate outcome
5. Final risk rating: LOW / MEDIUM / HIGH

Be specific and data-driven in your assessment.
""" + U["get_language_instruction"]()
        decision = invoke_llm_with_retry(llm, prompt).content
        return {"risk_facilitator_decision": decision,
                "risk_debate_state": {**rd, "facilitator_decision": decision}}

    return node


# ==========================================================================
# Portfolio manager (structured, final decision)
# ==========================================================================
def create_portfolio_manager(llm):
    from tradingagents.agents.schemas import PortfolioDecision, render_pm_decision
    from tradingagents.agents.utils.agent_utils import build_instrument_context, get_language_instruction
    from tradingagents.agents.utils.structured import bind_structured, invoke_structured_or_freetext

    structured_llm = bind_structured(llm, PortfolioDecision, "PortfolioManager")

    def node(state):
        company_name = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(company_name, asset_type)
        risk_history = state["risk_debate_state"].get("history", "")
        trader_plan = state.get("trader_investment_plan", "")
        past_context = state.get("past_context", "")
        investor_profile = state.get("investor_profile", "Aggressive")

        prompt_text = (
            f"You are the Portfolio Manager making the final investment decision for {company_name}. "
            f"{instrument_context}\n\n"
            f"Investor Profile: {investor_profile}\n\n"
            f"Review the risk analysts' debate and the trader's proposal, "
            f"then issue a final rating tailored to this investor profile.\n\n"
            f"Trader Proposal:\n{trader_plan[:800]}\n\n"
            f"Risk Analysts Debate:\n{risk_history[:1500]}\n\n"
        )
        if past_context:
            prompt_text += f"Past context:\n{past_context}\n\n"
        prompt_text += get_language_instruction()

        messages = [
            {"role": "system", "content": "You are a senior portfolio manager. Issue a final decision."},
            {"role": "user", "content": prompt_text},
        ]
        final_decision = None
        for attempt in range(3):
            try:
                final_decision = invoke_structured_or_freetext(
                    structured_llm, llm, messages, render_pm_decision, "PortfolioManager")
                break
            except Exception as e:  # noqa: BLE001
                if "429" in str(e) or "rate_limit" in str(e).lower():
                    time.sleep(60 * (attempt + 1))
                else:
                    raise
        return {"final_trade_decision": final_decision}

    return node


# ==========================================================================
# Macro Regime Analyst — market-wide risk regime (VIX / 10Y yield / DXY)
# ==========================================================================
MACRO_TICKERS = {
    "vix": "^VIX",       # fear gauge
    "tnx": "^TNX",       # 10Y treasury yield
    "dxy": "DX-Y.NYB",   # US dollar index
}


def fetch_macro_snapshot(as_of_date: str, lookback_days: int = 30) -> dict:
    """Latest VIX / 10Y yield / DXY plus their lookback-period average."""
    import yfinance as yf
    from datetime import datetime, timedelta

    end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=lookback_days)

    snapshot: dict = {}
    for key, ticker in MACRO_TICKERS.items():
        try:
            df = yf.download(
                ticker,
                start=start_dt.strftime("%Y-%m-%d"),
                end=(end_dt + timedelta(days=1)).strftime("%Y-%m-%d"),
                progress=False,
            )
            if df.empty:
                snapshot[key] = {"latest": None, "avg": None}
                continue
            # newer yfinance can return multi-level columns even for a
            # single ticker, making df["Close"] a 1-column DataFrame
            # instead of a Series -> float(Series) crashes. squeeze()
            # collapses a single column to a Series and is a no-op if it
            # already is one, so this works across yfinance versions.
            close = df["Close"].squeeze()
            latest = float(close.iloc[-1])
            avg = float(close.mean())
            snapshot[key] = {"latest": round(latest, 2), "avg": round(avg, 2)}
        except Exception as e:  # noqa: BLE001
            snapshot[key] = {"latest": None, "avg": None, "error": str(e)[:100]}
    return snapshot


def classify_macro_regime(snapshot: dict) -> str:
    """Rule-based macro tag: RISK_OFF_HIGH_VOL / RISK_ON_LOW_VOL /
    RATES_RISING / RATES_FALLING / NEUTRAL_MACRO. Deliberately separate from
    the stock-specific `classify_regime` in memory.py — this is market-wide,
    not ticker-specific, and is stored as its own episode metadata field so
    it never interferes with existing regime filtering."""
    vix = (snapshot.get("vix") or {}).get("latest")
    tnx = (snapshot.get("tnx") or {}).get("latest")
    tnx_avg = (snapshot.get("tnx") or {}).get("avg")

    if vix is not None:
        if vix >= 25:
            return "RISK_OFF_HIGH_VOL"
        if vix <= 15:
            return "RISK_ON_LOW_VOL"

    if tnx is not None and tnx_avg is not None and tnx_avg != 0:
        if tnx > tnx_avg * 1.03:
            return "RATES_RISING"
        if tnx < tnx_avg * 0.97:
            return "RATES_FALLING"

    return "NEUTRAL_MACRO"


# ✅ CHANGED (per explicit request): VIX/10Y/DXY above are US market
# indicators -- weak/indirect relevance to Dhaka Stock Exchange-listed
# companies (a US volatility spike doesn't necessarily say anything about
# DSE conditions). For DSE tickers, use the DSEX broad index's own trend +
# realized volatility instead -- the actual market this stock trades in.
# ✅ Endpoint confirmed via bdshare's own source code and its published
# PyPI/GitHub docs (not just assumed) -- get_market_info_more_data(start,
# end, code="DSEX") is the real, parameter-validated function for this
# (code is checked against {"DSEX","DSES","DS30","DGEN"} internally).
# Still fails soft (returns {}) rather than raising if the live request
# itself errors (network, dsebd.org downtime, markup change, etc.), so
# create_macro_regime_analyst below falls back to the VIX/TNX/DXY snapshot
# in that case -- check the logs after deploying to confirm which path
# fired on a real run.
def fetch_dse_macro_snapshot(as_of_date: str, lookback_days: int = 30) -> dict:
    """DSEX latest close + lookback-period average, plus realized daily
    volatility (DSE has no options-implied volatility index like VIX, so
    this is the closest available proxy for "how choppy is the market
    right now").

    🔴 FIXED (confirmed via bdshare's own source + PyPI docs, not just
    guessed): the previous version called market_data._fetch_dse_ohlcv
    ("DSEX", ...), which wraps bdshare.get_historical_data() -- that
    function's `code` param is for individual STOCK tickers ("ACI", "GP",
    ...), not index codes, so passing "DSEX" there was very likely
    silently returning nothing every time (triggering the fallback path
    below on every single run, never actually using DSE data). The
    correct, documented function for historical DSEX values is
    get_market_info_more_data(start, end, code="DSEX") -- confirmed in
    bdshare's own source: `code` is validated against exactly
    {"DSEX","DSES","DS30","DGEN"} and returns a Date + "DSEX Index"
    dataframe when code="DSEX" is passed."""
    from datetime import datetime, timedelta
    from bdshare import get_market_info_more_data

    end_dt = datetime.strptime(as_of_date, "%Y-%m-%d")
    start_dt = end_dt - timedelta(days=lookback_days)
    try:
        df = get_market_info_more_data(
            start_dt.strftime("%Y-%m-%d"), as_of_date, code="DSEX",
        )
    except Exception:  # noqa: BLE001
        return {}
    if df is None or df.empty or "DSEX Index" not in df.columns:
        return {}

    closes = [float(v) for v in df["DSEX Index"].tolist() if v not in (None, "")]
    if len(closes) < 2:
        return {}

    latest = closes[-1]
    avg = sum(closes) / len(closes)
    changes = [
        (closes[i] - closes[i - 1]) / closes[i - 1] * 100
        for i in range(1, len(closes)) if closes[i - 1]
    ]
    if changes:
        mean_chg = sum(changes) / len(changes)
        variance = sum((c - mean_chg) ** 2 for c in changes) / len(changes)
        volatility = variance ** 0.5
    else:
        volatility = 0.0

    return {
        "dsex": {"latest": round(latest, 2), "avg": round(avg, 2)},
        "dsex_volatility_pct": round(volatility, 2),
    }


def classify_dse_macro_regime(snapshot: dict) -> str:
    """Rule-based DSE-market regime tag from DSEX trend + realized
    volatility. Reuses the same tag vocabulary as classify_macro_regime
    (RISK_OFF_HIGH_VOL / RISK_ON_LOW_VOL / NEUTRAL_MACRO) so downstream
    code (regime-transition reflection, episode metadata) doesn't need a
    second tag set to handle -- RATES_RISING/RATES_FALLING are simply
    never emitted here since there's no comparable BD bond-yield signal
    wired in yet."""
    dsex = snapshot.get("dsex") or {}
    latest, avg = dsex.get("latest"), dsex.get("avg")
    vol = snapshot.get("dsex_volatility_pct")

    if vol is not None and vol >= 1.5:
        return "RISK_OFF_HIGH_VOL"
    if latest is not None and avg is not None and avg != 0 and (vol is None or vol < 1.0):
        if latest > avg * 1.02:
            return "RISK_ON_LOW_VOL"
    return "NEUTRAL_MACRO"


def create_macro_regime_analyst(llm, log=print):
    from langchain_core.messages import HumanMessage, SystemMessage
    from tradingagents.dataflows.symbol_utils import is_dse_ticker
    U = _ta_utils()

    def node(state):
        current_date = state["trade_date"]
        company = state.get("company_of_interest", "")
        log(f"Fetching macro snapshot for {current_date}")

        if is_dse_ticker(company):
            snapshot = fetch_dse_macro_snapshot(current_date)
            if snapshot:
                macro_regime = classify_dse_macro_regime(snapshot)
                log(f"DSEX={snapshot.get('dsex')} volatility={snapshot.get('dsex_volatility_pct')}%")
                log(f"macro regime (DSE): {macro_regime}")

                prompt = f"""You are a macro strategist covering the Dhaka Stock Exchange. Today is {current_date}.
Using the REAL data below, write a brief (3-4 sentence) macro market regime report
for the DSE broad market. Classify whether conditions are risk-on or risk-off and
what this implies for equity positioning on DSE-listed names.

=== DSE MACRO SNAPSHOT ===
DSEX Index:          latest={snapshot.get('dsex', {}).get('latest')}, 30d avg={snapshot.get('dsex', {}).get('avg')}
Realized volatility: {snapshot.get('dsex_volatility_pct')}% (daily, over the lookback window)

Rule-based macro regime tag: {macro_regime}
""" + U["get_language_instruction"]()

                messages = [
                    SystemMessage(content="You are a senior DSE market strategist. Base your report only on the data given."),
                    HumanMessage(content=prompt),
                ]
                report = invoke_llm_with_retry(llm, messages).content
                log("macro regime report ready (DSE)")
                return {"macro_report": report, "macro_regime": macro_regime, "macro_snapshot": snapshot}

            log("DSEX fetch failed/empty -- falling back to US VIX/10Y/DXY snapshot")

        snapshot = fetch_macro_snapshot(current_date)
        macro_regime = classify_macro_regime(snapshot)
        log(f"VIX={snapshot.get('vix')} 10Y={snapshot.get('tnx')} DXY={snapshot.get('dxy')}")
        log(f"macro regime: {macro_regime}")

        prompt = f"""You are a macro strategist. Today is {current_date}.
Using the REAL data below, write a brief (3-4 sentence) macro market regime report.
Classify whether conditions are risk-on or risk-off, whether rates are rising or
falling, and what this implies for equity positioning.

=== MACRO SNAPSHOT ===
VIX (fear gauge):      latest={snapshot.get('vix', {}).get('latest')}, 30d avg={snapshot.get('vix', {}).get('avg')}
10Y Treasury Yield:    latest={snapshot.get('tnx', {}).get('latest')}, 30d avg={snapshot.get('tnx', {}).get('avg')}
US Dollar Index (DXY): latest={snapshot.get('dxy', {}).get('latest')}, 30d avg={snapshot.get('dxy', {}).get('avg')}

Rule-based macro regime tag: {macro_regime}
""" + U["get_language_instruction"]()

        messages = [
            SystemMessage(content="You are a senior macro strategist. Base your report only on the data given."),
            HumanMessage(content=prompt),
        ]
        report = invoke_llm_with_retry(llm, messages).content
        log("macro regime report ready")

        return {"macro_report": report, "macro_regime": macro_regime, "macro_snapshot": snapshot}

    return node


# ==========================================================================
# Post-Mortem / Self-Critique — cross-regime review of resolved episodes
# ==========================================================================
def _safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def run_post_mortem(company: str, memory, llm, log=print) -> tuple[str, int]:
    """Structured self-critique over ALL of a company's RESOLVED episodes,
    across every regime — unlike the regime-transition reflection (which
    only fires on a regime change and only looks at the prior regime), this
    runs every session so the Trader/Portfolio Manager always see the full
    track record. Returns (lessons_text, episodes_reviewed)."""
    episodes = memory.gather_resolved_episodes(company)
    if not episodes:
        return "(Post-mortem skipped — no RESOLVED episodes yet.)", 0

    wins = [e for e in episodes if _safe_float(e.get("pnl_pct")) > 0]
    losses = [e for e in episodes if _safe_float(e.get("pnl_pct")) < 0]

    lines = [
        f"- {e.get('trade_date', '?')}: Signal={e.get('final_signal', '?')}, "
        f"Regime={e.get('regime', '?')}, P&L={e.get('pnl_pct', '?')}%, "
        f"Outcome={e.get('outcome_label', '?')}"
        for e in episodes
    ]
    history_text = "\n".join(lines)

    prompt = (
        f"You are a trading post-mortem analyst reviewing {company}'s last {len(episodes)} "
        f"RESOLVED trading decisions across all market regimes:\n\n{history_text}\n\n"
        f"Win count: {len(wins)}, Loss count: {len(losses)}\n\n"
        f"In 4-5 concise bullet points, identify:\n"
        f"1. Any pattern in which regimes/signals tend to lose money.\n"
        f"2. Whether the system is systematically too aggressive or too conservative.\n"
        f"3. One concrete process adjustment for future Trader/Portfolio Manager decisions.\n"
        f"Base this ONLY on the data above — do not invent numbers."
    )
    log(f"reviewing {len(episodes)} resolved episodes ({len(wins)}W/{len(losses)}L)")
    try:
        result = invoke_llm_with_retry(llm, prompt).content.strip()
        log("post-mortem ready")
        return result, len(episodes)
    except Exception as e:  # noqa: BLE001
        return f"(Post-mortem LLM call failed: {e})", len(episodes)


def create_post_mortem_agent(llm, memory, log=print):
    def node(state):
        company = state["company_of_interest"]
        lessons, n_reviewed = run_post_mortem(company, memory, llm, log=log)
        return {"post_mortem_lessons": lessons, "post_mortem_n_episodes": n_reviewed}

    return node


# ==========================================================================
# Decision Verifier / Fact-Check — post-decision sanity check
# ==========================================================================
# Runs after the Portfolio Manager's final decision. Nine agents chain off
# each other's output sequentially, so an early hallucination/bad number can
# propagate all the way to the final call — this catches that in 3 layers:
#   1) rule-based sanity check   — RSI/news sentiment vs. the final signal
#   2) numeric contradiction     — DETERMINISTIC (regex + tolerance), not
#      LLM-judged: a small local model repeatedly misjudged decimal
#      rounding as a "genuine difference" (e.g. 68.17 vs 68.16905...), so
#      arithmetic comparison is never handed to the LLM.
#   3) LLM semantic check        — ADVISORY ONLY (SIGNAL_CONSISTENT y/n).
#      The 7B model over-triggered on ordinary hedge/caveat language, so
#      this alone can never flip status to FLAGGED.
def rule_based_checks(final_signal: str, indicators: dict, news_metrics: dict,
                      fundamentals_report: str = "") -> tuple[list[str], list[str]]:
    """Returns (warnings, info_notes). Warnings flag status; info_notes are
    shown for transparency but never change status."""
    warnings: list[str] = []
    info_notes: list[str] = []

    fund_verdict = extract_final_proposal(fundamentals_report)
    fund_verdict_upper = fund_verdict.upper() if fund_verdict else ""
    fund_agrees_with_final = bool(fund_verdict) and final_signal in fund_verdict_upper

    def _add(msg: str):
        (info_notes if fund_agrees_with_final else warnings).append(msg)

    rsi = indicators.get("rsi")
    try:
        rsi_val = float(rsi)
        if rsi_val >= 70 and final_signal == "BUY":
            _add(f"RSI={rsi_val} is overbought (>=70) but signal is BUY — possible contradiction.")
        if rsi_val <= 30 and final_signal == "SELL":
            _add(f"RSI={rsi_val} is oversold (<=30) but signal is SELL — possible contradiction.")
    except (TypeError, ValueError):
        pass

    overall_sent = str(news_metrics.get("overall_sentiment", "")).lower()
    if "negative" in overall_sent and final_signal == "BUY":
        _add("News sentiment is negative but signal is BUY — worth verifying.")
    if "positive" in overall_sent and final_signal == "SELL":
        _add("News sentiment is positive but signal is SELL — worth verifying.")

    if fund_agrees_with_final and info_notes:
        info_notes.append(
            "The technical/sentiment contradiction(s) above were NOT flagged because the "
            f"Fundamentals Analyst's own hard verdict ({fund_verdict}) already agrees with "
            "the final signal — i.e. strong fundamentals legitimately override soft "
            "sentiment/technical signals."
        )

    if fund_verdict:
        if "SELL" in fund_verdict_upper and final_signal == "BUY":
            warnings.append(
                f"Fundamentals Analyst said SELL ({fund_verdict}) but the final signal is BUY — "
                "the debate/trader/PM chain overrode that verdict; needs direct review."
            )
        elif "BUY" in fund_verdict_upper and final_signal == "SELL":
            warnings.append(
                f"Fundamentals Analyst said BUY ({fund_verdict}) but the final signal is SELL — "
                "the debate/trader/PM chain overrode that verdict; needs direct review."
            )
        elif "HOLD" in fund_verdict_upper and final_signal in ("BUY", "SELL"):
            warnings.append(
                f"Fundamentals Analyst said HOLD ({fund_verdict}) but the final signal is {final_signal} — "
                "the debate/trader/PM chain moved off a neutral fundamentals verdict without a hard "
                "SELL/BUY basis for doing so; needs direct review."
            )

    return warnings, info_notes


def _extract_cited_number(text: str, label_patterns: list[str]) -> float | None:
    """Finds the number written near a label (e.g. "RSI") in the decision
    text. First match wins.

    Tolerates natural-language connectors between the label and the number
    (e.g. "RSI at 68.17", "RSI is currently 68.17", "RSI stands at 68.17"),
    not just "RSI: 68.17" / "RSI = 68.17" — an LLM writing prose almost never
    uses the strict label+colon form, so a stricter pattern here would make
    this check silently never fire in practice. The <=20-char gap cap keeps
    it from skipping past to an unrelated number further down the text.
    """
    for label in label_patterns:
        m = re.search(rf"{label}\b(?:\s*\([^)]*\))?[^0-9\-]{{0,20}}(-?\d+\.?\d*)", text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                continue
    return None


def check_numeric_contradiction(final_decision_text: str, indicators: dict,
                                fund_metrics: dict, skip_eps: bool = False) -> list[str]:
    """Compares every number the decision text cites against the raw
    ground-truth value, with a generous rounding tolerance (2% relative or
    0.5 absolute) so "same number, fewer decimals" is never confused with a
    genuinely wrong figure. Pure Python — no LLM arithmetic judgment.

    ✅ CHANGED: `skip_eps` -- confirmed live (BATBC) that DSE tickers
    routinely have SEVERAL simultaneously-valid, genuinely-different EPS
    figures on the books at once (Q1-only, H1 cumulative, prior-year
    comparative, last full audited year -- e.g. BATBC's own disclosures
    show 3.88 for Q1 2026 alone vs a cumulative/derived ~7.65 for H1).
    fund_metrics only ever holds ONE of these. A tolerance check assumes
    there's a single ground truth the decision text should match, which
    doesn't hold here -- the LLM legitimately citing a *different*,
    equally-real EPS figure than the one in fund_metrics isn't an error,
    and this check has no way to tell that apart from an actual
    hallucinated number. Set skip_eps=True (DSE tickers) rather than
    guess a looser tolerance, since no fixed tolerance is principled when
    the two numbers are correctly describing different reporting
    periods. RSI/MACD/P-E aren't affected -- those remain single-valued
    for a given ticker+date."""
    checks = [
        ("RSI", ["RSI"], indicators.get("rsi")),
        ("MACD", ["MACD"], indicators.get("macd")),
        ("P/E Ratio", ["P/E Ratio", "P/E"], fund_metrics.get("pe_ratio")),
    ]
    if not skip_eps:
        checks.append(("EPS (TTM)", [r"EPS \(TTM\)", "EPS"], fund_metrics.get("eps_ttm")))
    mismatches = []
    for label, patterns, raw in checks:
        if raw in (None, "", "N/A"):
            continue
        try:
            raw_val = float(raw)
        except (TypeError, ValueError):
            continue
        cited = _extract_cited_number(final_decision_text, patterns)
        if cited is None:
            continue
        diff = abs(cited - raw_val)
        tolerance = max(0.5, 0.02 * abs(raw_val))
        if diff > tolerance:
            mismatches.append(
                f"{label}: decision text says {cited}, raw data says {raw_val} "
                f"(diff={diff:.2f}, tolerance={tolerance:.2f}) — possible genuine mismatch."
            )
    return mismatches


def llm_signal_consistency_check(final_decision_text: str, llm) -> str:
    """The one genuinely subjective/semantic question — is the decision
    text's own reasoning self-consistent? Result is advisory-only (see
    run_decision_verifier); a 7B model's opinion here doesn't get to FLAG a
    run on its own."""
    prompt = f"""You are a fact-checking auditor reviewing a trading decision before it is finalized.

=== FINAL DECISION TEXT ===
{final_decision_text[:1200]}

Check ONLY this one thing:

Respond with ONE strict marker line FIRST (machine-parsed), THEN your explanation
— do not paraphrase the marker:
SIGNAL_CONSISTENT: YES or NO

RULES (read carefully before answering):
- HOLD is a legitimate, self-consistent conclusion whenever the inputs are mixed --
  e.g. overbought/oversold technicals pulling one way while fundamentals or news
  sentiment pull the other way. Mentioning a caution/risk factor and then still
  making a call (BUY/HOLD/SELL) is NORMAL trading commentary, not an inconsistency.
- Only answer NO if the decision text's OWN stated reasoning DIRECTLY and STRONGLY
  contradicts its OWN action -- e.g. the text says "this is a clear sell signal" or
  "there is no reason to buy" but then names BUY as the action. A hedge like
  "shows some overbought risk but still has growth potential" followed by BUY is
  CONSISTENT, not a contradiction -- do not flag it.
- Default to YES unless the contradiction is obvious and severe.

Then, in 1-2 short bullet points, if SIGNAL_CONSISTENT is NO, quote the specific
phrase in the decision text whose own reasoning contradicts its own action.

Be concise and only flag REAL, severe discrepancies -- do not invent problems.
"""
    try:
        return invoke_llm_with_retry(llm, prompt).content.strip()
    except Exception as e:  # noqa: BLE001
        return f"(LLM fact-check failed: {e})"


def run_decision_verifier(final_decision_text: str, indicators: dict, fund_metrics: dict,
                          news_metrics: dict, fundamentals_report: str, llm,
                          is_dse: bool = False, log=print) -> dict:
    """Runs all three checks and returns VERIFIED/FLAGGED status.

    ✅ CHANGED (per explicit request): the rule-based fundamentals-
    contradiction check is now advisory-only, same as the LLM semantic
    check -- still computed and shown in `notes` for transparency, but it
    no longer flips `status` to FLAGGED and no longer auto-overrides
    `effective_signal` to HOLD. Only the deterministic numeric-
    contradiction check and the LLM call itself failing/not following the
    expected format can flag status now. If you want the old
    contradiction-blocks-the-trade behavior back, that's a one-line
    revert: re-add `rule_warnings` to the `status =` line below and
    restore the auto-override block that used to follow it (see git
    history / prior version of this function)."""
    sig_match = re.search(r"\*{0,2}(BUY|HOLD|SELL)\*{0,2}", final_decision_text, re.IGNORECASE)
    final_signal = sig_match.group(1).upper() if sig_match else "N/A"

    log("running rule-based checks (advisory only -- does not flag status)")
    rule_warnings, rule_info_notes = rule_based_checks(
        final_signal, indicators, news_metrics, fundamentals_report=fundamentals_report)

    log("running deterministic numeric-contradiction check")
    numeric_mismatches = check_numeric_contradiction(
        final_decision_text, indicators, fund_metrics, skip_eps=is_dse)

    log("running advisory LLM semantic check")
    llm_notes = llm_signal_consistency_check(final_decision_text, llm)

    llm_call_failed = "(llm fact-check failed" in llm_notes.lower()
    signal_consistent_m = re.search(r"SIGNAL_CONSISTENT:\s*(YES|NO)", llm_notes, re.IGNORECASE)
    markers_missing = signal_consistent_m is None

    # Status is decided only by hard/reliable signals: code-verified
    # numeric mismatch, or the LLM call failing/not following the format.
    # Both the rule-based fundamentals-contradiction check AND the LLM's
    # own SIGNAL_CONSISTENT opinion are advisory and never flip status.
    status = "FLAGGED" if (numeric_mismatches or llm_call_failed or markers_missing) else "VERIFIED"

    notes_parts = []
    if rule_warnings:
        notes_parts.append("Rule-based (advisory, does NOT affect status): " + " | ".join(rule_warnings))
    if rule_info_notes:
        notes_parts.append("Rule-based (info, non-flagging): " + " | ".join(rule_info_notes))
    if numeric_mismatches:
        notes_parts.append("Numeric check (code, non-LLM): " + " | ".join(numeric_mismatches))
    notes_parts.append("LLM semantic check (advisory, does NOT affect status): " + llm_notes)
    notes = "\n".join(notes_parts)

    # ✅ CHANGED: auto-override removed along with the status effect -- an
    # "advisory, does not affect status" check silently forcing the
    # actionable signal to HOLD anyway would be a confusing half-state
    # (VERIFIED status, but the real signal changed underneath it).
    # effective_signal now always matches final_signal.
    effective_signal = final_signal
    auto_overridden = False

    log(f"verification status: {status}")
    return {
        "status": status, "notes": notes, "final_signal": final_signal,
        "effective_signal": effective_signal, "auto_overridden": auto_overridden,
    }


def create_decision_verifier(llm, log=print):
    def node(state):
        final_text = state.get("final_trade_decision", "")
        indicators = state.get("indicators_parsed", {})
        fund_metrics = state.get("fund_metrics", {})
        news_metrics = state.get("news_metrics", {})
        fundamentals_report = state.get("fundamentals_report", "")
        from tradingagents.dataflows.symbol_utils import is_dse_ticker
        is_dse = is_dse_ticker(state.get("company_of_interest", ""))
        result = run_decision_verifier(
            final_text, indicators, fund_metrics, news_metrics, fundamentals_report,
            llm, is_dse=is_dse, log=log)
        return {"verification_result": result}

    return node
