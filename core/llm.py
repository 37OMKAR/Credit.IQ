"""LLM layer: any OpenAI-compatible provider + a task router that keeps cost per document low.

Cost controls built in:
  * disk cache   - the same prompt is never paid for twice (re-runs, report refreshes are free)
  * compression  - page text is whitespace-squeezed before sending (OCR text is ~20-30% spaces)
  * routing      - cheap model for extraction / tagging, 'heavy' model only for the narrative
  * ledger       - every call's tokens and estimated cost are recorded and shown in the app
"""
import csv
import hashlib
import json
import os
import re
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(HERE, "cases", "llm_cache")
PRICE_FILE = os.path.join(HERE, "data", "llm_prices.csv")

PROVIDERS = {
    "DeepSeek": {"base_url": "https://api.deepseek.com", "model": "deepseek-flash", "env": "DEEPSEEK_API_KEY"},  # deepseek-chat retired Jul-2026
    "LongCat": {"base_url": "https://api.longcat.ai/openai", "model": "LongCat-2.5-Preview", "env": "LONGCAT_API_KEY"},  # per LongCat quick-start, Oct 2026
    "OpenRouter": {"base_url": "https://openrouter.ai/api/v1", "model": "deepseek/deepseek-chat", "env": "OPENROUTER_API_KEY"},
    "OpenAI": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini", "env": "OPENAI_API_KEY"},
    "Google Gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "model": "gemini-2.5-flash", "env": "GEMINI_API_KEY"},
    "Anthropic Claude": {"base_url": "https://api.anthropic.com/v1/", "model": "claude-sonnet-4-5", "env": "ANTHROPIC_API_KEY"},
    "Groq": {"base_url": "https://api.groq.com/openai/v1", "model": "llama-3.3-70b-versatile", "env": "GROQ_API_KEY"},
    "Ollama (local, offline)": {"base_url": "http://localhost:11434/v1", "model": "qwen2.5:14b", "env": "OLLAMA_API_KEY"},
    "Custom (OpenAI-compatible)": {"base_url": "", "model": "", "env": "CUSTOM_API_KEY"},
}

# ledger shared by every LLM instance in the process
LEDGER = []


class LLMError(Exception):
    pass


def load_prices():
    """USD per 1M tokens (input, output). Editable in data/llm_prices.csv."""
    out = {}
    try:
        with open(PRICE_FILE, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    out[r["model"].strip().lower()] = (float(r["usd_per_m_input"]), float(r["usd_per_m_output"]))
                except (ValueError, KeyError):
                    pass
    except FileNotFoundError:
        pass
    return out


def squeeze(text):
    """Cut tokens without losing table structure: collapse runs of spaces, drop blank lines."""
    text = re.sub(r"[ \t]{2,}", "  ", text or "")
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


class LLM:
    def __init__(self, provider="DeepSeek", api_key=None, base_url=None, model=None, temperature=0.1, timeout=180,
                 use_cache=True):
        cfg = PROVIDERS.get(provider, PROVIDERS["Custom (OpenAI-compatible)"])
        self.provider = provider
        self.base_url = base_url or cfg["base_url"]
        self.model = model or cfg["model"]
        self.api_key = api_key or os.getenv(cfg["env"]) or ("ollama" if "Ollama" in provider else None)
        self.temperature = temperature
        self.timeout = timeout
        self.use_cache = use_cache
        self._client = None
        self.task = ""
        self.fallbacks = []   # other configured models tried when this one can't return usable JSON
        self.case_id = None

    @property
    def ready(self):
        return bool(self.api_key and self.base_url and self.model)

    @property
    def label(self):
        return f"{self.provider} / {self.model}"

    def client(self):
        if self._client is None:
            from openai import OpenAI
            headers = {"HTTP-Referer": "http://localhost:8501", "X-Title": "Credit Intelligence Workbench"} if self.provider == "OpenRouter" else None
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout, default_headers=headers)
        return self._client

    def _cache_path(self, payload):
        h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:40]
        return os.path.join(CACHE_DIR, f"{h}.json")

    def chat(self, system, user, json_mode=False, max_tokens=4000, retries=2):
        if not self.ready:
            raise LLMError("No API key configured. Add it in the sidebar or in the .env file.")
        user = squeeze(user)
        payload = {"m": self.model, "u": self.base_url, "s": system, "q": user, "j": json_mode}
        cp = self._cache_path(payload)
        if self.use_cache and os.path.exists(cp):
            try:
                with open(cp, encoding="utf-8") as f:
                    content = json.load(f)["content"]
                LEDGER.append({"task": self.task, "case": self.case_id, "provider": self.provider, "model": self.model, "in": 0, "out": 0, "cached": True})
                return content
            except Exception:
                pass
        kwargs = dict(model=self.model, temperature=self.temperature, max_tokens=max_tokens,
                      messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        if json_mode and "Anthropic" not in self.provider:
            kwargs["response_format"] = {"type": "json_object"}
        if self.provider == "LongCat" and os.getenv("LONGCAT_THINKING", "off").lower() != "on":
            # LongCat models reason before answering: without this it "thinks" for minutes and can run out of tokens before the answer
            kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        last = None
        for attempt in range(retries + 1):
            try:
                r = self.client().chat.completions.create(**kwargs)
                msg = r.choices[0].message
                content = msg.content or ""
                if not content.strip():  # some reasoning models put everything in a separate field
                    extra = getattr(msg, "model_extra", None) or {}
                    content = extra.get("reasoning_content") or extra.get("reasoning") or ""
                self.last_finish = getattr(r.choices[0], "finish_reason", None)
                u = getattr(r, "usage", None)
                actual = None
                if u is not None:  # OpenRouter returns the real charge in usage.cost (USD)
                    actual = getattr(u, "cost", None)
                    if actual is None and getattr(u, "model_extra", None):
                        actual = u.model_extra.get("cost")
                LEDGER.append({"task": self.task, "case": self.case_id, "provider": self.provider, "model": self.model,
                               "in": (u.prompt_tokens or 0) if u else 0, "out": (u.completion_tokens or 0) if u else 0, "cached": False,
                               "usd_actual": float(actual) if actual is not None else None, "gen_id": getattr(r, "id", None)})
                if self.use_cache and content:
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    with open(cp, "w", encoding="utf-8") as f:
                        json.dump({"content": content}, f)
                return content
            except Exception as e:  # network / rate-limit / bad-format
                last = e
                if "response_format" in kwargs and ("response_format" in str(e) or "json" in str(e).lower()):
                    kwargs.pop("response_format")  # model doesn't support JSON mode
                if "extra_body" in kwargs and "think" in str(e).lower():
                    kwargs.pop("extra_body")  # model doesn't accept the thinking switch
                time.sleep(2 * (attempt + 1))
        raise LLMError(f"{self.provider} call failed: {last}")

    def chat_json(self, system, user, max_tokens=6000):
        """JSON reply; if this model's reply can't be read, retry once (no cache), then try the other configured models."""
        sysj = system + "\nReturn ONLY valid JSON. No markdown fences, no commentary, no reasoning text."
        errors = []
        for llm in [self] + [f for f in (self.fallbacks or []) if f is not self]:
            for attempt in range(2 if llm is self else 1):
                old_cache = llm.use_cache
                llm.use_cache = old_cache and attempt == 0
                llm.task = self.task
                llm.case_id = self.case_id
                try:
                    raw = llm.chat(sysj, user, json_mode=True, max_tokens=max_tokens)
                    out = parse_json(raw)
                    if llm is not self:
                        out["_model_used"] = llm.label
                    return out
                except Exception as e:
                    why = str(e)
                    if getattr(llm, "last_finish", None) == "length":
                        why += " (reply cut off at the length limit)"
                    errors.append(f"{llm.label}: {why[:120]}")
                    try:  # never keep an unusable reply in the cache
                        os.remove(llm._cache_path({"m": llm.model, "u": llm.base_url, "s": sysj, "q": squeeze(user), "j": True}))
                    except Exception:
                        pass
                finally:
                    llm.use_cache = old_cache
        raise LLMError("No usable JSON - " + " | ".join(errors))

    def test(self):
        old, self.use_cache = self.use_cache, False
        try:
            return self.chat("You are a test endpoint.", "Reply with the single word OK.", max_tokens=5).strip()
        finally:
            self.use_cache = old


# ------------------------------------------------------------------ task router
TASKS = {
    "extract": "Statement extraction (balance sheet / P&L / cash flow)",
    "notes": "Auditor report & notes review",
    "brsr": "BRSR extraction",
    "support": "Supporting-documents review",
    "news": "News tagging & brief",
    "narrative": "Credit narrative (report writing)",
}
LIGHT_TASKS = ("extract", "notes", "brsr", "support", "news")


class Router:
    """Picks a configured LLM per task. mode: 'cheapest' | 'balanced' | 'quality'."""

    def __init__(self, llms, assignment=None, mode="cheapest"):
        self.llms = {k: v for k, v in llms.items() if v is not None and v.ready}
        self.assignment = assignment or {}
        self.mode = mode

    @property
    def ready(self):
        return bool(self.llms)

    def get(self, task):
        name = self.assignment.get(task)
        llm = self.llms.get(name) if name else None
        if llm is None and self.llms:
            llm = next(iter(self.llms.values()))
        if llm is not None:
            llm.task = task
            llm.fallbacks = [v for v in self.llms.values() if v is not llm]
        return llm

    def describe(self):
        return {t: (self.get(t).label if self.get(t) else "rule-based (no AI)") for t in TASKS}


def ledger_summary(prices=None, case_id=None):
    prices = prices or load_prices()
    rows = {}
    for e in LEDGER:
        if case_id is not None and e.get("case") != case_id:
            continue
        k = (e["provider"], e["model"])
        r = rows.setdefault(k, {"provider": e["provider"], "model": e["model"], "calls": 0, "cached": 0, "in": 0, "out": 0, "usd": 0.0,
                                "actual_calls": 0, "estimated_calls": 0})
        r["calls"] += 1
        r["cached"] += 1 if e.get("cached") else 0
        r["in"] += e["in"]
        r["out"] += e["out"]
        if e.get("cached"):
            continue
        if e.get("usd_actual") is not None:  # billed amount reported by the provider (OpenRouter)
            r["usd"] += e["usd_actual"]
            r["actual_calls"] += 1
            continue
        r["estimated_calls"] += 1
        p = prices.get(e["model"].lower()) or prices.get(e["model"].lower().replace(":online", ""))
        if p:
            r["usd"] += e["in"] / 1e6 * p[0] + e["out"] / 1e6 * p[1]
        r["usd"] += e.get("search_usd", 0.0)
        if e["model"].endswith(":online"):
            r["usd"] += 0.02
    return list(rows.values())


def list_models(provider, api_key, base_url=None):
    """Model ids this key can use, read live from the provider (OpenAI-compatible /models)."""
    from openai import OpenAI
    base = base_url or PROVIDERS.get(provider, {}).get("base_url")
    cl = OpenAI(api_key=api_key, base_url=base, timeout=30)
    return sorted({m.id for m in cl.models.list().data})


def _repair_truncated(t):
    stack, in_str, esc, last_ok = [], False, False, None
    for i, ch in enumerate(t):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
            last_ok = (i, list(stack))
        elif ch == "," and not in_str:
            last_ok = (i - 1, list(stack))
    if last_ok is None:
        return None
    i, st = last_ok
    cand = re.sub(r",\s*$", "", t[:i + 1]) + "".join(reversed(st))
    try:
        return json.loads(cand)
    except Exception:
        return None


def parse_json(raw):
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).strip()
    raw = re.sub(r"```$", "", raw).strip()
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()  # reasoning models
    if "</think>" in raw:
        raw = raw.split("</think>")[-1].strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, flags=re.S)
    if m:
        raw = m.group(1)
    try:
        return json.loads(raw)
    except Exception:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        frag = raw[start:end + 1]
        try:
            return json.loads(frag)
        except Exception:
            frag = re.sub(r",\s*([}\]])", r"\1", frag)  # trailing commas
            try:
                return json.loads(frag)
            except Exception:
                pass
    if start != -1:  # reply cut off: close the open brackets and keep what is complete
        rep = _repair_truncated(raw[start:])
        if rep is not None:
            return rep
    raise LLMError("Model did not return JSON")


def case_cost(case_id, fx=88.0):
    rows = ledger_summary(case_id=case_id)
    usd = sum(r["usd"] for r in rows)
    act = sum(r["actual_calls"] for r in rows)
    est = sum(r["estimated_calls"] for r in rows)
    return {"usd": usd, "inr": usd * fx, "calls": sum(r["calls"] for r in rows), "cached": sum(r["cached"] for r in rows), "rows": rows,
            "actual_calls": act, "estimated_calls": est,
            "basis": "billed by OpenRouter" if act and not est else ("estimate from price list" if est and not act else
                                                                    ("mixed: OpenRouter billed + estimate" if act else "no AI calls"))}


def openrouter_account(api_key, timeout=15):
    """Live OpenRouter key usage / limit (USD) - shown in Settings and Admin."""
    import requests
    out = {}
    for path in ("key", "credits"):
        try:
            r = requests.get(f"https://openrouter.ai/api/v1/{path}", headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
            if r.ok:
                out[path] = r.json().get("data") or {}
            else:
                out[path + "_error"] = f"HTTP {r.status_code}: {r.text[:160]}"
        except Exception as e:
            out[path + "_error"] = str(e)[:160]
    return out
