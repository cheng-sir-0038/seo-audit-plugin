# International SEO Semantics

Use only when the user or evidence involves multilingual/multi-regional URLs, `hreflang`, locale targeting, language selectors, or international migrations.

Current `PageInspection` preserves hreflang alternates from both HTML `<link rel="alternate" hreflang>` and repeated HTTP `Link` headers as `hreflang + resolved URL + source`. `HreflangAssessment` is a diagnosis-layer cluster evaluator, not a new Provider Capability.

## Required facts

For each localized URL under inspection, preserve:

- URL, status/final URL, indexability;
- document language;
- canonical;
- every hreflang target and language/region code;
- self-reference;
- return link from alternate pages;
- `x-default` when present;
- implementation surface (HTML, HTTP Link header, Sitemap) when known.

Do not infer correctness from `lang` alone. A target URL that has not been inspected remains unknown: source-page markup cannot prove the target status, indexability, canonical, or return link.

## Hreflang cluster rules

A healthy cluster should normally satisfy:

1. every localized page declares itself plus intended alternates;
2. alternate relationships are reciprocal;
3. language/region/script values are syntactically supported;
4. targets resolve to the intended URLs and are not broken/redirecting unexpectedly;
5. canonical signals do not collapse distinct regional pages into an unrelated URL;
6. `x-default` is treated as fallback, not as a language code;
7. the cluster represents genuinely localized user experiences, not arbitrary duplicate URLs.

Do not require `x-default` for every site; report it as recommended only when a sensible unmatched-language fallback exists.

The deterministic evaluator currently checks:

- missing hreflang declarations;
- missing self-reference;
- malformed language/region syntax;
- the same hreflang code pointing to multiple URLs;
- target HTTP success and noindex when the target has been inspected;
- reciprocal return links;
- localized pages canonicalizing to another URL;
- presence of `x-default` without treating it as mandatory.

## Canonical interaction

Same-language regional variants can be highly similar. Do not diagnose hreflang in isolation from canonicalization when one version canonicalizes to another. Distinguish:

- intended regional variants;
- accidental duplicates;
- translated pages;
- language selector/fallback pages.

## Automatic redirects

If users/bots are automatically redirected by IP, locale, cookie, or browser language, verify that crawlable localized URLs still exist and that the redirect does not prevent access to alternate versions. A redirect policy is not automatically wrong; the question is whether Google/users can consistently reach the intended URLs.

## User-facing output

Prefer:

> 德语页面指向英语页面，但英语页面没有返回指向德语页面，因此这两个版本的语言/地区对应关系不完整。

Avoid implementation jargon such as “reciprocity matrix failure” unless the user asks for technical detail.

## Official facts source
