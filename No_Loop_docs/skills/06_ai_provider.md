# Skill: AI Provider Engineer (06)

**Load for:** LOOP-3/LOOP-4 provider work, BYOK integration, local-model adapter.
**Reads:** MASTER_SPEC §12, RESEARCH.md S7, DATA_SOURCES.md §3, AGENT_RULES R-SEC-1/3, skill 02 standards.

## Role
Maintain the provider abstraction. No API key is mandatory. Support no-AI, BYOK, and optional local inference. Never expose secrets to logs. Make provider privacy behavior visible.

## Provider protocol (binding interface)
```
available() -> bool
generate(prompt: GenerationRequest) -> GenerationResult
structured_generate(request, schema: Type[T]) -> T          # validated output
explain(match: MatchResult, profile_subset) -> Explanation  # human-readable factors
estimate_cost(request) -> CostEstimate                      # tokens/$/time where applicable
privacy_info() -> PrivacyInfo                               # what data goes where, stored where
```

## Built-in tiers (S7)
1. **NoAIProvider** — always available; every caller must degrade gracefully through it.
2. **RuleBasedProvider** — template + selection NLG over confirmed facts; deterministic; powers no-key email/summary drafting (LOOP-7 no-AI path).
3. **BYOK providers** (UserProvidedGeminiProvider + OpenAI-compatible generic) — key entered by user, stored via keyring (`CredentialReference`), never bundled, never logged; request payloads logged only as sizes/hashes.
4. **LocalModelProvider** — Ollama/llama.cpp-compatible HTTP; only used if the user's own runtime is present; auto-disabled when total RAM < 8 GB (measured RAM needs: ~1B ≈ 1–2 GB, 3B ≈ 2.5–4 GB, 8B ≈ 5–7 GB — DATA_SOURCES §3); never installed by No_Loop; model downloads are the user's, redirected off C: by their own configuration (dev note: ENVIRONMENT §2).

## Mandatory behaviors
- **Privacy panel:** before first activation of any non-local provider, render `privacy_info()`: destination, data categories (e.g. "profile subset + JD text"), retention unknown/known, user consent required (R-SEC-3, DPDP baseline).
- **Slicing:** never send the whole resume repeatedly; send requirement-relevant fact slices (MASTER_SPEC §13).
- **Validation:** `structured_generate` outputs validated against schema; failures → rule-based fallback, never silent garbage.
- **Cost/time caps:** per-call timeout; per-day request budget settings; cancelable UI operations.
- **Fallback chain:** BYOK failure → RuleBased → NoAI, with visible status in UI ("AI unavailable — using rule-based drafting").
- **Provenance:** AI-generated text is marked as AI-assisted in artifacts; factual fields still come only from confirmed facts (S2 — AI never fabricates facts; it may rephrase selected facts).

## Test discipline
- Contract tests against fake/local stub servers (no real network in tests).
- Fallback-chain tests; redaction tests (assert no key material in logs/caps).
- Memory-gate test for LocalModelProvider.

## Guardrails
Never hard-code one vendor into services (registry + port only). Never store keys in DB/settings files. Never send unconfirmed/inferred facts to any provider. Never claim local model works on 2 GB machines.

## Deliverables
Provider registry, tier implementations, privacy panel data, fallback tests, ledger entry.
