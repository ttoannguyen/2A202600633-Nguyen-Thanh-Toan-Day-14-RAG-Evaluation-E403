# Báo cáo Lab — Day 14: AI Evaluation & Benchmarking

**Môn học:** AICB-P1 — AI Practical Competency Program, Phase 1
**Chủ đề:** Evaluation Pipeline cho RAG/AI Agent — RAGAS-style metrics, LLM-as-Judge, Benchmark, Failure Analysis
**Sinh viên:** Nguyễn Thành Toàn — 2A202600633
**File liên quan:** [`template.py`](./template.py), [`solution/solution.py`](./solution/solution.py), [`tests/test_solution.py`](./tests/test_solution.py), [`exercises.md`](./exercises.md), [`reflection.md`](./reflection.md)

---

## 1. Mục tiêu

Xây dựng 1 pipeline đánh giá (evaluation pipeline) hoàn chỉnh cho AI agent theo đúng vòng đời:

```
Hypothesis → Experiment → Measure → Conclude → Iterate
```

gồm 5 thành phần: **data model** (golden dataset), **RAGAS-style evaluator** (answer-side + retrieval-side), **LLM-as-Judge**, **benchmark runner** (với regression detection), và **failure analyzer** (root cause + improvement log). Sau đó dùng pipeline này để tự xây 1 golden dataset 20 câu, chạy benchmark, và phân tích thất bại bằng phương pháp 5 Whys.

---

## 2. Phần 2 — Cài đặt mã nguồn (Core Coding)

Toàn bộ TODO trong `template.py` đã được implement và copy sang `solution/solution.py`. **39/39 unit test pass** (`python3 -m unittest tests.test_solution` — môi trường không có `pytest` cài sẵn nên dùng `unittest`, cùng test suite).

### 2.1 Task 1 — Data Models

- `QAPair`: `question`, `expected_answer`, `context: str = ""`, `metadata: dict`, `retrieved_contexts: list` — dataclass cho 1 cặp hỏi-đáp trong golden dataset.
- `EvalResult`: `qa_pair`, `actual_answer`, `faithfulness`, `relevance`, `completeness`, `passed`, `failure_type`, `context_precision`, `context_recall` — kết quả đánh giá 1 câu.
- `overall_score()` = `(faithfulness + relevance + completeness) / 3.0`.

### 2.2 Task 2 — RAGASEvaluator (answer-side, word-overlap heuristic)

Cả 3 hàm dùng chung nguyên lý: tokenize (bỏ stopword) → tính tỉ lệ giao nhau giữa 2 tập token, clamp [0, 1], trả `1.0` nếu vế chia bằng rỗng (tránh chia 0 và tránh phạt oan câu hỏi/context rỗng):

| Hàm | Công thức |
|-----|-----------|
| `evaluate_faithfulness(answer, context)` | `\|answer ∩ context\| / \|answer\|` |
| `evaluate_relevance(answer, question)` | `\|answer ∩ question\| / \|question\|` |
| `evaluate_completeness(answer, expected)` | `\|answer ∩ expected\| / \|expected\|` |

### 2.3 Task 2b — Retrieval-side metrics (chấm bước *get context*)

- `evaluate_context_recall(contexts, expected)`: hợp (union) token của toàn bộ chunk, so với token của expected answer — đo retriever có **lấy đủ** evidence không, không quan tâm thứ tự.
- `evaluate_context_precision(contexts, expected, relevance_threshold=0.1)`: cài **Average Precision (AP@K)** đúng chuẩn RAGAS — chunk được đánh dấu "relevant" nếu tỉ lệ overlap với expected ≥ threshold; sau đó cộng `Precision@k` tại mọi vị trí có chunk relevant rồi chia cho tổng số chunk relevant. Đây là điểm khác biệt mấu chốt: **rank-aware**, nên đổi vị trí chunk sẽ đổi điểm.
- `rerank_by_overlap(contexts, query)`: sort chunk theo `len(tokenize(chunk) ∩ tokenize(query))` giảm dần — reranker lexical đơn giản, dùng để minh chứng Exercise 3.5.
- `run_full_eval(...)`: gọi 3 hàm answer-side, xác định `passed` (cả 3 ≥ 0.5) và `failure_type` theo thứ tự ưu tiên: `faithfulness < 0.3` → `hallucination`; `relevance < 0.3` → `irrelevant`; `completeness < 0.3` → `incomplete`; còn lại nếu fail → `off_topic`.

### 2.4 Task 3 — LLMJudge

- `score_response(question, answer, rubric)`: build prompt gồm câu hỏi, câu trả lời, và rubric; gọi `judge_llm_fn(prompt)`; parse JSON trả về `{"scores": {...}, "reasoning": raw}` — nếu parse lỗi, fallback `0.5` cho mọi criterion (an toàn, không crash pipeline).
- `detect_bias(scores_batch)`: tính điểm trung bình mỗi entry; `leniency_bias` nếu avg > 0.8, `severity_bias` nếu avg < 0.3; `positional_bias` so sánh entry đầu với trung bình các entry còn lại (lệch > 0.1 → có bias).

### 2.5 Task 4 — BenchmarkRunner

- `run(qa_pairs, agent_fn, evaluator)`: với mỗi `QAPair`, gọi `agent_fn(question)` lấy answer, rồi `evaluator.run_full_eval(...)`; gán lại `result.qa_pair = pair` để giữ `metadata` gốc (vì `run_full_eval` tự tạo `QAPair` mới không có metadata).
- `generate_report(results)`: `total`, `passed`, `pass_rate`, `avg_faithfulness/relevance/completeness`, `failure_types` (đếm theo loại).
- `run_regression(new_results, baseline_results)`: so trung bình từng metric giữa run mới và baseline; **regression** nếu baseline cao hơn new > 0.05; trả `regressions: list[str]` + `passed: bool`.
- `identify_failures(results, threshold=0.5)`: trả các `EvalResult` có **bất kỳ** metric nào dưới threshold.

### 2.6 Task 5 — FailureAnalyzer

- `categorize_failures`: đếm theo `failure_type`.
- `find_root_cause(failure)`: nếu ≥ 2 metric dưới 0.5 → `"Multiple issues detected — review full pipeline"`; ngược lại map metric thấp nhất sang câu gợi ý cụ thể (faithfulness → retrieval, relevance → prompt clarity, completeness → context window/generation).
- `generate_improvement_suggestions(failures)`: map từng `failure_type` sang 1 suggestion cụ thể, đảm bảo trả về ≥ 3 suggestion (bù bằng danh sách fallback nếu thiếu).
- `generate_improvement_log(failures, suggestions)`: build bảng Markdown `Failure ID | Type | Root Cause | Suggested Fix | Status (Open)`.

### 2.7 Kết quả kiểm thử

```
$ python3 -m unittest tests.test_solution -v
...
Ran 39 tests in 0.001s
OK
```

Toàn bộ 39 test (RAGASEvaluator, Context Metrics, BenchmarkRunner, FailureAnalyzer, LLMJudge, EvalResult.overall_score, run_regression, generate_improvement_log) đều **pass**.

---

## 3. Phần 1 — Lý thuyết (Warm-up)

Trả lời đầy đủ trong [`exercises.md`](./exercises.md#part-1--warm-up-00002000), tóm tắt:

- **1.1 RAGAS thresholds:** với mỗi metric (Faithfulness, Answer Relevancy, Context Recall, Context Precision, Completeness) đã xác định rõ khi nào low score là *acceptable* (style drift, thiếu detail phụ) vs *critical* (hallucination, miss core fact, ranking hỏng) kèm action cụ thể (block deploy, tune retriever/reranker, v.v.).
- **1.2 Position Bias:** thiết kế experiment 2-condition (hoán đổi vị trí 2 câu trả lời, giữ nguyên nội dung) để đo % lần judge đổi ý chỉ vì đổi thứ tự; đề xuất fix Verbosity Bias bằng tiêu chí "conciseness" tách riêng; giải thích lý do bắt buộc calibrate-against-human (judge có thể tự tin nhưng sai hệ thống).
- **1.3 CI/CD:** đề xuất threshold cụ thể (Faithfulness 0.7, Relevancy 0.6, Completeness 0.6) kèm lý do; phân biệt rõ offline eval (gate trước deploy) vs online eval (monitor liên tục sau deploy).

---

## 4. Phần 3 — Golden Dataset, Benchmark, Rubric, Reranking

### 4.1 Golden Dataset (Exercise 3.1)

**Domain chọn:** *AI/RAG Assistant* — trợ lý hỏi-đáp kỹ thuật AI/RAG cho engineer (bám sát nội dung lecture Day 14, dễ kiểm chứng đúng/sai).

20 QA pairs theo stratified sampling đúng tỉ lệ đề bài: **5 Easy** (factual lookup), **7 Medium** (multi-step reasoning), **5 Hard** (ambiguous/trade-off), **3 Adversarial** (out-of-scope, prompt injection, ambiguous trap). Toàn bộ nội dung chi tiết (question, expected_answer, context, source_doc/attack_type) nằm trong [`exercises.md` § Exercise 3.1](./exercises.md#exercise-31--build-your-golden-dataset-stratified-sampling).

### 4.2 Benchmark Run (Exercise 3.2)

Chạy `BenchmarkRunner.run()` thật trên 20 QA pairs với 1 **simulated agent**: trả lời đúng (paraphrase question+context+expected) cho phần lớn câu, nhưng cố tình hỏng 4 câu để có failure thực tế: `M06` (hallucinate — khẳng định ngược), `H02` (incomplete — bỏ qua xử lý conflict), `A01` (không refuse out-of-scope), `A03` (overclaim sai trên câu ambiguous).

**Kết quả tổng hợp:**

| Metric | Giá trị |
|--------|---------|
| Pass rate | **30%** (6/20) |
| Avg Faithfulness | **0.41** (Significant Issues) |
| Avg Relevance | 0.90 (Good) |
| Avg Completeness | 0.82 (Good) |
| Failure types | off_topic: 10, hallucination: 2, irrelevant: 1, incomplete: 1 |

**3 câu điểm thấp nhất:** `A01` (0.11), `M06` (0.26), `H02` (0.28) — đều là các câu bị **cố tình hỏng**, xác nhận pipeline phát hiện đúng vấn đề thật.

**Insight quan trọng phát hiện được:** 10/20 câu bị gán nhãn `off_topic` dù Relevance = Completeness = 1.00 — nguyên nhân thật là Faithfulness rơi vào dải biên 0.33–0.47 (dưới ngưỡng pass 0.5 nhưng **không** dưới 0.3). Logic `run_full_eval` chỉ có 4 nhánh kiểm tra `< 0.3`, bỏ sót dải 0.3–0.5, nên rơi vào nhánh "else" và gán nhãn `off_topic` — **sai về ý nghĩa** (lỗi thật là "grounding yếu", không phải "lạc đề"). Đây là 1 hạn chế thật của failure-taxonomy 4-nhánh, được dùng làm luận điểm chính trong phần Reflection.

### 4.3 LLM-as-Judge Rubric (Exercise 3.3)

Rubric 5 mức cho domain AI/RAG, mỗi mức có tiêu chí cụ thể + ví dụ response thật (không chỉ mô tả chung). Chọn 4 criteria dimension: Correctness, Completeness, Relevance, Citation, Safety (bỏ Tone/Actionability vì không phù hợp domain Q&A kỹ thuật). Liệt kê 3 edge case khó chấm điểm (câu ambiguous, paraphrase sâu, refusal đúng/sai) kèm cách xử lý cụ thể trong rubric. Chi tiết: [`exercises.md` § Exercise 3.3](./exercises.md#exercise-33--llm-as-judge-rubric-design).

### 4.4 Reranking — Context Recall vs Precision (Exercise 3.5)

Chạy thật `evaluate_context_recall` / `evaluate_context_precision` / `rerank_by_overlap` trên 5 query R01–R05 (noise đặt trước, evidence relevant bị chôn):

| | Trước rerank | Sau rerank |
|---|---|---|
| Context Recall (avg) | 0.80 | 0.80 *(không đổi)* |
| Context Precision (avg) | 0.55 | **0.97** (+0.42) |

**Kết luận rút ra (đã verify bằng số liệu thật, không phải lý thuyết suông):**
1. Recall không đổi sau rerank vì được tính trên **union** token của toàn bộ chunk — reranking chỉ đổi thứ tự, không đổi tập chunk.
2. Precision tăng mạnh vì là **rank-aware** (Average Precision @K) — đưa chunk relevant lên đầu làm `Precision@k` tăng sớm.
3. Khi Recall thấp (R04 = 0.57, R05 = 0.62) thì rerank vô dụng — phải sửa retriever (tăng top-k, hybrid search, query expansion) trước, vì evidence vốn không có trong tập chunk.

Đề xuất pipeline tối ưu Precision: *hybrid search (top-50) → cross-encoder rerank → giữ top-5 → MMR khử trùng lặp*. Chi tiết đầy đủ + bảng kỹ thuật get-context: [`exercises.md` § Exercise 3.5](./exercises.md#exercise-35--tăng-context-precision-bằng-reranking-nâng-cao).

### 4.5 Bước 6 (Tuỳ chọn) — Reranker tự viết

Viết `rerank_by_expected_coverage(contexts, expected)`: chấm chunk theo overlap với **expected answer** (đúng định nghĩa "relevant" mà `evaluate_context_precision` dùng, thay vì theo query như `rerank_by_overlap`) và **phạt chunk dài** (chia cho `len(chunk_tokens) + 1`). Đo lại trên R01–R05:

| ID | Precision (before) | + `rerank_by_overlap` | + `rerank_by_expected_coverage` |
|----|---|---|---|
| Avg | 0.55 | 0.97 | **1.00** |

Vượt `rerank_by_overlap` đúng ở điểm yếu của nó (R01: 0.83 → 1.00) — vì optimize trực tiếp theo expected thay vì theo query (query/answer thường paraphrase lệch wording). **Caveat:** đây là reranker kiểu *oracle* (cần `expected`, không có lúc inference thật) — chỉ dùng để đo upper-bound/offline labeling, không deploy production được. Chi tiết: [`exercises.md` § Bước 6](./exercises.md#tuỳ-chọn-bước-6--viết-reranker-của-riêng-bạn).

### 4.6 Exercise 3.4 (Bonus) — Framework Comparison: RAGAS vs DeepEval (cài thật)

Đã cài thật `ragas==0.4.3` và `deepeval==4.0.6` trong sandbox (không có `python3-dev`/sudo nên phải dùng `pip install --only-binary=:all:`; `ragas` còn cần pin `langchain-community==0.3.27` vì bản mới hơn xoá module mà `ragas.llms.base` import cứng). Sandbox **không có API key LLM**, nên không chạy được các metric LLM-judge chủ lực (`Faithfulness`/`AnswerRelevancy` của cả 2 framework) — so sánh dưới đây chạy thật trên **metric non-LLM** của mỗi framework, trên 10 câu từ golden dataset 3.1 (script: [`exercise_3_4_framework_compare.py`](./exercise_3_4_framework_compare.py)).

| Tiêu chí | RAGAS (`NonLLMStringSimilarity`) | DeepEval (`Scorer.rouge_score`) |
|---|---|---|
| Setup | Nặng, cần patch version | Sạch, 1 lần, có sẵn `pytest` |
| Strictness | **Strict hơn** — character-level (Jaro-Winkler), penalize nặng câu đúng nhưng paraphrase khác chữ | Khoan dung hơn — n-gram/word-based, gần với heuristic Lab |
| Avg score (10 câu) | 0.286 | 0.286 (trùng trung bình, khác hẳn per-row) |
| Failure agreement (threshold 0.5/0.3) | Flag **10/10** "fail" (kể cả 6 câu đúng) | Flag **6/10** "fail" — khớp đúng 4 câu cố tình hỏng + 2 câu lệch nhiều |

**Insight:** cả 2 framework đồng thuận tốt ở 4 câu **cố tình hỏng** (M06/H02/A01/A03 — đều chấm thấp nhất), nhưng RAGAS's non-LLM metric quá strict để tách "sai" khỏi "đúng nhưng diễn đạt khác" — minh hoạ rõ lý do production cần metric LLM-judge (semantic) thay vì string-similarity thuần. Chi tiết đầy đủ + bảng 10 dòng: [`exercises.md` § Exercise 3.4](./exercises.md#exercise-34--framework-comparison-bonus).

---

## 5. Phần 4 — Reflection & Failure Analysis

Toàn văn trong [`reflection.md`](./reflection.md), tóm tắt các điểm chính:

### 5.1 Top 3 failures — 5 Whys

| # | Câu hỏi | Overall | Root cause thật (sau 5 Whys) |
|---|---------|---------|-------------------------------|
| 1 | A01 — "Weather in Tokyo?" (out-of-scope) | 0.11 | Thiếu **hard scope-gate** trước generation — guardrail chỉ là soft prompt instruction |
| 2 | M06 — "Why recall alone isn't enough?" | 0.26 | Thiếu **self-verification step** — model phát biểu claim ngược context mà không bị chặn |
| 3 | H02 — Conflicting retrieved chunks | 0.28 | Thiếu **few-shot/reasoning depth** cho câu hỏi Hard-tier — agent default về shortcut |

Với cả 3 case, `find_root_cause()` đều trả về **"Multiple issues detected"** (generic) vì rule chỉ nhìn pattern điểm số (≥2 metric < 0.5). Phân tích tay (đọc nội dung answer) cho thấy mỗi case thực ra có **1 root cause duy nhất** gây hiệu ứng domino lên cả 3 metric — đây là hạn chế cố hữu của root-cause-by-score-pattern, được ghi nhận rõ trong báo cáo.

### 5.2 Failure Clustering

3 cluster: **(1) Weak faithfulness guardrail** (12/14 failures — lớn nhất, ưu tiên High, chọn fix đầu tiên vì kéo điểm tổng thể nhiều nhất và sửa luôn lỗi nhãn `off_topic`), **(2) Missing scope-gate** (2 failures, High vì safety-critical), **(3) Thiếu reasoning depth Hard-tier** (1 failure, Medium).

### 5.3 CI/CD & Regression Strategy

- `run_regression()` nên chạy ở mọi PR/merge, mọi đổi prompt/retrieval config, trước demo/launch.
- Threshold 0.05 hợp lý cho Relevance/Completeness nhưng nên **strict hơn (0.03)** cho Faithfulness vì đây là metric yếu nhất của hệ thống.
- Block deploy nếu regression chạm Faithfulness hoặc case Adversarial; chỉ alert cho Relevance/Completeness ở case không an toàn-critical.
- Flow đề xuất: `Code change → Run benchmark (offline eval) → generate_report + run_regression vs baseline → Quality gate (block/alert) → Deploy`.

### 5.4 Continuous Improvement & Framework Choice

3 action ưu tiên kế tiếp: self-verification step (faithfulness), scope-gate (adversarial), few-shot conflict-handling (Hard-tier). Đề xuất chuyển sang **RAGAS thật** (LLM/embedding-based) cho production — vì lab đã chứng minh bằng số liệu thật giới hạn của word-overlap heuristic (10/20 case bị chấm sai do lexical mismatch dù nội dung đúng).

---

## 6. Kết luận

- Toàn bộ pipeline evaluation (data model → answer-side & retrieval-side metrics → LLM judge → benchmark runner → failure analyzer) đã implement đầy đủ, pass **39/39 unit test**.
- Golden dataset 20 câu (stratified, có adversarial) đã được xây và benchmark thật, không phải số liệu giả định — pass rate 30%, bottleneck rõ ràng ở Faithfulness (0.41).
- Phân tích 5 Whys + clustering cho thấy 3 root cause độc lập (thiếu scope-gate, thiếu self-verification, thiếu few-shot reasoning), và đồng thời phát hiện 1 hạn chế thật của framework (failure-taxonomy 4-nhánh bỏ sót dải biên 0.3–0.5) — insight này được dùng làm luận cứ chính cho khuyến nghị chuyển sang RAGAS thật ở production.
- Exercise 3.5 (reranking) verify bằng số liệu thật: Precision tăng +0.42 sau rerank, Recall giữ nguyên — đúng lý thuyết rank-aware AP@K; reranker tự viết (Bước 6) đẩy lên 1.00.
- Exercise 3.4 (Bonus): cài thật RAGAS + DeepEval, đo non-LLM metrics — RAGAS strict hơn DeepEval rõ rệt (character-level vs n-gram), cả 2 đồng thuận tốt ở 4 failure case cố tình hỏng.

## 7. Submission Checklist

- [x] All tests pass: `pytest tests/ -v` (39/39 — ban đầu chạy `python3 -m unittest tests.test_solution` vì môi trường không có `pytest`; sau khi cài `deepeval` cho Exercise 3.4, `pytest` có sẵn theo và cũng chạy 39/39 pass thật)
- [x] `overall_score` implemented
- [x] `run_regression` implemented
- [x] `generate_improvement_log` implemented
- [x] `evaluate_context_recall` + `evaluate_context_precision` implemented (Task 2b)
- [x] Exercise 3.5 completed: đo Context Recall/Precision + reranking before/after + Bước 6 (custom reranker)
- [x] Exercise 3.4 (Bonus) completed: cài thật ragas + deepeval, so sánh non-LLM metrics
- [x] `exercises.md` completed: golden dataset 20 QA (stratified) + benchmark results + rubric
- [x] `reflection.md` written: 3 failures with 5 Whys + improvement log + CI/CD strategy
- [x] `solution/solution.py` copied
