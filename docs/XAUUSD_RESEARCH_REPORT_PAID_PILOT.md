# QROS XAUUSD Research Report — Paid Pilot Offer

**Status:** Offer draft for customer discovery. This document is not evidence that the service is deployed or ready to accept customer data or payments.

## The offer

QROS is testing a narrowly scoped research service for independent XAUUSD researchers and systematic traders who need reproducible analysis rather than trade calls.

For one agreed XAUUSD dataset and one pre-defined research question, the pilot deliverable is a research report that records:

- the dataset identity and SHA-256 content hash;
- the exact research question, assumptions, methodology, and evaluation window;
- the observed result, including a null or inconclusive result;
- uncertainty and limitations, including data-quality issues;
- evidence references and reproducibility details available from the run;
- validation status and a clear distinction between tested facts and unverified hypotheses.

The report is research context only. It is not financial advice, a buy/sell signal, a guarantee of predictive accuracy, or an instruction to execute trades. QROS does not place broker orders.

## Proposed first-pilot scope

- One customer, one workspace, one agreed dataset, one pre-registered research question.
- One initial report and one short review call.
- Any follow-up run, new dataset, or materially changed question is separately agreed.
- Delivery date and final scope are confirmed only after the data, question, and environment are reviewed.
- Synthetic fixtures may be used to demonstrate plumbing, but are never presented as real-market evidence.

## Price discovery — hypotheses, not established prices

Do not advertise these as proven market rates. Test willingness to pay with qualified prospects before fixing a price.

| Test offer | Hypothesis price | Scope |
|---|---:|---|
| Introductory report | ₮150,000 | One dataset, one question, one report |
| Research pilot | ₮350,000 | One dataset, one question, report plus review call |
| Extended pilot | ₮700,000 | Pre-agreed additional validation or one follow-up analysis |

The prices are discovery probes, not commitments. Confirm actual delivery cost, support time, tax/invoicing obligations, and customer expectations before accepting payment. Do not take payment or customer data until the relevant release, access-control, privacy, and delivery gates have passed.

## Who this is for

- Independent XAUUSD researchers.
- Systematic traders who want to test a specific hypothesis reproducibly.
- Small research teams that need traceable datasets, assumptions, and results.

It is not for customers seeking guaranteed returns, an automated signal service, broker execution, or a claim that a strategy is profitable without appropriate out-of-sample and cost-aware evidence.

## Customer-discovery questions

Ask before offering a price:

1. What specific XAUUSD research question are you trying to answer?
2. What do you currently use to test it, and what is difficult to reproduce?
3. What evidence would make a report useful enough to pay for?
4. Which data can you lawfully provide, and what restrictions apply?
5. Would you pay ₮150,000, ₮350,000, or ₮700,000 for the corresponding scope? Why or why not?
6. What would prevent you from using the result?
7. If the result is null or inconclusive, would the reproducibility and evidence still be valuable?

Record the respondent's actual answers. Do not count polite interest, a demo, a checkout session, or a verbal compliment as revenue.

## Outreach message (Mongolian)

Сайн байна уу. Би XAUUSD-ийн судалгааны үр дүнг таамаглал хэлбэрээр бус, ашигласан өгөгдөл, SHA-256 hash, аргачлал, тодорхойгүй байдал, хязгаарлалтыг нь мөрдөж шалгах боломжтой тайлан болгон гаргах QROS судалгааны үйлчилгээг туршиж байна.

Энэ нь buy/sell дохио, ашиг амлалт, эсвэл автомат арилжаа биш. Нэг тодорхой XAUUSD судалгааны асуултаар эхний туршилтын хэрэглэгчдийн хэрэгцээг судалж байна.

Та одоо ямар XAUUSD таамаглалыг шалгах гэж байгаа, одоогийн аргачлалын тань хамгийн том хүндрэл юу вэ гэдгийг 15 минут ярилцаж болох уу? Хэрэгцээ таарвал хамрах хүрээ, өгөгдлийн шаардлага, үнийг урьдчилан тохирно. Үйлчилгээний аюулгүй ажиллагаа болон өгөгдөл тусгаарлах шалгалтууд баталгаажаагүй үед хэрэглэгчийн бодит өгөгдөл авахгүй.

## Release gates before paid delivery

- [ ] Exact candidate SHA and all required CI checks recorded.
- [ ] Staging schema/migration parity has a reviewed disposition.
- [ ] Two separate authenticated identities prove workspace and private-storage isolation.
- [ ] Deployed Golden Path passes: sign-in → workspace → dataset upload → immutable version/hash → research run → worker completion → report/evidence retrieval.
- [ ] Output is checked against an independent fixture and provenance hashes.
- [ ] Backup/restore and recovery evidence is recorded.
- [ ] Public HTTPS, operational logging, rate limits, private artifact access, and support/stop procedure are verified.
- [ ] Data ownership, consent, retention, and secure intake are agreed with the customer.
- [ ] If online payment is used, Stripe test-mode checkout, webhook signature, idempotency, subscription/entitlement lifecycle, cancellation/refund behavior, and usage limits pass before live mode.

If a gate fails, do not accept customer data or payment for a service that cannot yet be delivered safely. Continue discovery interviews without implying readiness.

## Pilot outcome record

- Prospect / date:
- Research question:
- Dataset source and permission:
- Agreed scope and price:
- Candidate SHA / environment:
- Dataset ID / version / SHA-256:
- Request ID / run ID:
- Report and evidence references:
- Operator time / compute cost:
- Customer usefulness feedback:
- Paid (yes/no; transaction evidence recorded securely outside this repository):
- Follow-up decision:
