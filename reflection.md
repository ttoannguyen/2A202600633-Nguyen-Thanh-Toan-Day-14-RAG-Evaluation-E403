# Day 14 — Reflection
## Evaluation Report & Failure Analysis

---

## 1. Benchmark Results Summary

Paste results từ Exercise 3.2 và tóm tắt:

**Overall pass rate:** 30% (6/20)

**Average scores:**

| Metric | Average | Min | Max | Std Dev |
|--------|---------|-----|-----|---------|
| Faithfulness | 0.41 | 0.00 | 0.80 | 0.18 |
| Relevance | 0.90 | 0.20 | 1.00 | 0.25 |
| Completeness | 0.82 | 0.00 | 1.00 | 0.37 |
| Overall Score | 0.71 | 0.11 | 0.93 | 0.23 |

**Score interpretation (theo bài giảng):**
- Bao nhiêu metrics ở Good (0.8–1.0)? 2 (Relevance avg 0.90, Completeness avg 0.82) — overall avg 0.71 không tính vì rơi vào Needs Work
- Bao nhiêu metrics ở Needs Work (0.6–0.8)? 1 (Overall avg 0.71)
- Bao nhiêu metrics ở Significant Issues (<0.6)? 1 (Faithfulness avg 0.41) — đây là bottleneck thật của hệ thống

**Failure type distribution:**

| Failure Type | Count | Percentage |
|--------------|-------|------------|
| hallucination | 2 | 10% |
| irrelevant | 1 | 5% |
| incomplete | 1 | 5% |
| off_topic | 10 | 50% |
| refusal | 0 | 0% |

> Lưu ý: nhãn `off_topic` (50%) phần lớn là mislabel — root cause thật của các case này là Faithfulness rơi vào dải 0.3–0.5 (grounding yếu, không phải "lạc đề"). Failure taxonomy 4-nhánh hiện tại chỉ check `< 0.3` nên gán nhãn sai cho dải biên này. Xem mục 3 để phân tích đúng cluster.

---

## 2. Top 3 Worst Failures — 5 Whys Analysis

Theo bài giảng: "Phân loại failure TRƯỚC KHI fix. Đừng fix từng failure riêng lẻ — CLUSTER rồi fix root cause."

### Failure 1

**Question:** What's the weather like in Tokyo today? *(adversarial — out-of-scope)*

**Agent Answer:** "It is sunny and 25 degrees Celsius in Tokyo today."

**Scores:** Faithfulness: 0.00 | Relevance: 0.33 | Completeness: 0.00 | Overall: 0.11

**5 Whys Analysis:**
| Level | Question | Answer |
|-------|----------|--------|
| Symptom | Vấn đề là gì? | Agent trả lời 1 câu hỏi out-of-scope bằng thông tin bịa đặt thay vì refuse |
| Why 1 | Tại sao xảy ra? | Agent không nhận ra câu hỏi nằm ngoài phạm vi hệ thống (AI/RAG assistant) |
| Why 2 | Tại sao Why 1 xảy ra? | Không có bước kiểm tra scope/intent tách biệt trước khi generate — chỉ dựa vào system prompt mô tả phạm vi |
| Why 3 | Tại sao Why 2 xảy ra? | System prompt chỉ là soft instruction ("you are specialized in...") — LLM vẫn có thể "cố giúp" và bịa câu trả lời khi câu hỏi nghe như factual lookup bình thường |
| Why 4 | Root cause là gì? | Thiếu hard gate (scope classifier) chạy TRƯỚC generation; guardrail hiện tại hoàn toàn phụ thuộc vào "good behavior" của LLM dưới prompt mềm |

**Root cause (from `find_root_cause()`):**
> "Multiple issues detected — review full pipeline" (cả 3 metric đều < 0.5)

**Bạn có đồng ý với root cause suggestion không? Tại sao?**
> Đồng ý một phần. Function đúng khi gắn cờ severity cao (cả 3 metric tệ), nhưng nhãn "multiple issues — review full pipeline" quá chung, không actionable. Đọc nội dung answer thực tế cho thấy đây là 1 root cause DUY NHẤT (thiếu scope-gate) gây hiệu ứng domino làm cả 3 metric đều thấp — không phải 3 vấn đề độc lập. `find_root_cause()` chỉ nhìn pattern điểm số nên không phân biệt được "1 root cause lan toả" vs "3 root cause thật sự khác nhau".

**Proposed fix (cụ thể, actionable):**
> 1. Thêm 1 bước scope/intent classifier chạy trước generation, trigger templated refusal khi câu hỏi out-of-scope.
> 2. Bổ sung thêm adversarial out-of-scope examples vào golden dataset (đã có A01–A03 trong lab này) làm regression test bắt buộc trong CI/CD.

---

### Failure 2

**Question:** Why can't context recall alone tell you if a RAG system is good?

**Agent Answer:** "Context recall alone proves the RAG system is fully correct and ready for production."

**Scores:** Faithfulness: 0.30 | Relevance: 0.42 | Completeness: 0.05 | Overall: 0.26

**5 Whys Analysis:**
| Level | Question | Answer |
|-------|----------|--------|
| Symptom | Agent khẳng định 1 kết luận SAI — ngược hoàn toàn với expected answer (recall cao ≠ system tốt) |
| Why 1 | Tại sao xảy ra? | Agent không tích hợp đầy đủ thông tin trong context (context nói rõ recall phải đi kèm precision/faithfulness) |
| Why 2 | Tại sao Why 1 xảy ra? | Agent generate câu trả lời 1 chiều, tự tin, không đối chiếu lại với context trước khi emit |
| Why 3 | Tại sao Why 2 xảy ra? | Prompt không yêu cầu self-check/verify claim against context trước khi trả lời |
| Why 4 | Root cause là gì? | Thiếu faithfulness guardrail (verification step) trong generation pipeline — model có thể phát biểu claim không được context support mà không bị chặn |

**Root cause (from `find_root_cause()`):**
> "Multiple issues detected — review full pipeline"

**Bạn có đồng ý với root cause suggestion không? Tại sao?**
> Không hoàn toàn. Đây thực chất là 1 case hallucination/faithfulness thuần túy (claim sai, không grounded) — completeness và relevance thấp chỉ là HẬU QUẢ của việc nội dung sai (answer lệch hoàn toàn khỏi expected_answer nên token overlap thấp), không phải 3 nguyên nhân độc lập. `find_root_cause()` dùng rule "≥2 metric thấp → multiple issues" nên bỏ sót quan hệ nhân-quả giữa các metric.

**Proposed fix:**
> 1. Thêm bước self-verification ("claim này có suy ra trực tiếp từ context không?") trước khi finalize answer.
> 2. Thêm contradiction/hallucination checker so khớp polarity của claim với reference answer cho các câu hỏi dạng "tại sao X không đủ/không tốt".

---

### Failure 3

**Question:** A user asks a question answerable from two retrieved chunks that slightly contradict each other — what should the agent do?

**Agent Answer:** "The agent should just pick one of the chunks and answer with it."

**Scores:** Faithfulness: 0.43 | Relevance: 0.20 | Completeness: 0.20 | Overall: 0.28

**5 Whys Analysis:**
| Level | Question | Answer |
|-------|----------|--------|
| Symptom | Answer quá ngắn/hời hợt, bỏ qua đúng phần khó của câu hỏi (xử lý conflict) |
| Why 1 | Tại sao xảy ra? | Agent chọn shortcut (pick 1 chunk) thay vì engage với khía cạnh "contradiction" được hỏi |
| Why 2 | Tại sao Why 1 xảy ra? | Prompt/template không có hướng dẫn xử lý tình huống evidence mâu thuẫn |
| Why 3 | Tại sao Why 2 xảy ra? | Không có few-shot example minh hoạ hành vi "flag conflict" cho câu hỏi Hard-tier |
| Why 4 | Root cause là gì? | Thiếu instruction + few-shot cho reasoning-depth ở câu hỏi phức tạp — agent default về hành vi đơn giản nhất (chọn 1 nguồn) |

**Root cause (from `find_root_cause()`):**
> "Multiple issues detected — review full pipeline"

**Bạn có đồng ý với root cause suggestion không? Tại sao?**
> Một phần. Faithfulness 0.43 chỉ hơi dưới ngưỡng (không phải nguyên nhân chính); driver thật là completeness/relevance rất thấp vì answer bỏ qua hoàn toàn phần lập luận khó. Root cause thực tế chính xác hơn nên là "Answer is missing key information — increase context window or improve generation" (completeness là vấn đề chính), không phải "multiple issues" generic.

**Proposed fix:**
> 1. Thêm few-shot examples minh hoạ cách xử lý conflicting evidence (cite cả 2, flag discrepancy) vào prompt cho Hard-tier questions.
> 2. Dùng chain-of-thought prompting riêng cho câu hỏi Hard/Adversarial để buộc agent suy luận đủ bước trước khi trả lời ngắn gọn.

---

## 3. Failure Clustering

Theo bài giảng: "Fix 1 root cause giải quyết nhiều failures cùng lúc."

**Cluster Analysis:**

| Cluster | Root Cause | Failures in cluster | Priority |
|---------|-----------|--------------------:|----------|
| 1 | Weak faithfulness guardrail — no self-verification/grounding check before generation | 12 (10 mislabeled `off_topic` + M06 + A02, tất cả có faithfulness 0.30–0.47) | High |
| 2 | Missing scope-gate for adversarial/out-of-scope inputs | 2 (A01, A03) | High (safety-critical dù count nhỏ) |
| 3 | Thiếu few-shot/reasoning depth cho câu hỏi Hard-tier (conflict handling) | 1 (H02) | Medium |

**Nếu chỉ fix 1 cluster, bạn chọn cluster nào? Tại sao?**
> Cluster 1 — weak faithfulness guardrail. Đây là cluster lớn nhất (12/14 failures), và Faithfulness là metric DUY NHẤT rơi vào "Significant Issues" (avg 0.41 < 0.6) trong toàn bộ benchmark — fix root cause này (thêm self-verification step) sẽ kéo điểm tổng thể lên nhiều nhất, đồng thời giải quyết luôn vấn đề nhãn `off_topic` sai (Mục 1) vì những case đó vốn chỉ thiếu grounding chứ không lạc đề.

---

## 4. Improvement Log (from `generate_improvement_log`)

Output của `generate_improvement_log()` (14 failures, threshold=0.5):

```
| Failure ID | Type | Root Cause | Suggested Fix | Status |
|------------|------|------------|---------------|--------|
| F001 | off_topic | Context is missing or irrelevant — improve retrieval | Implement hallucination checker to filter unsupported claims | Open |
| F002 | off_topic | Context is missing or irrelevant — improve retrieval | Add few-shot examples and clarify prompt to keep answers on-topic | Open |
| F003 | off_topic | Context is missing or irrelevant — improve retrieval | Increase chunk size in RAG pipeline to reduce context fragmentation | Open |
| F004 | off_topic | Context is missing or irrelevant — improve retrieval | Improve intent detection to route to the correct skill | Open |
| F005 | incomplete | Multiple issues detected — review full pipeline | Improve intent detection to route to the correct skill | Open |
| F006 | off_topic | Context is missing or irrelevant — improve retrieval | Improve intent detection to route to the correct skill | Open |
| F007 | off_topic | Context is missing or irrelevant — improve retrieval | Improve intent detection to route to the correct skill | Open |
| F008 | irrelevant | Multiple issues detected — review full pipeline | Improve intent detection to route to the correct skill | Open |
| F009 | off_topic | Context is missing or irrelevant — improve retrieval | Improve intent detection to route to the correct skill | Open |
| F010 | off_topic | Context is missing or irrelevant — improve retrieval | Improve intent detection to route to the correct skill | Open |
| F011 | off_topic | Context is missing or irrelevant — improve retrieval | Improve intent detection to route to the correct skill | Open |
| F012 | hallucination | Multiple issues detected — review full pipeline | Improve intent detection to route to the correct skill | Open |
| F013 | off_topic | Context is missing or irrelevant — improve retrieval | Improve intent detection to route to the correct skill | Open |
| F014 | hallucination | Multiple issues detected — review full pipeline | Improve intent detection to route to the correct skill | Open |
```

**Thêm 3 improvement suggestions từ `generate_improvement_suggestions()`:**
1. Implement hallucination checker to filter unsupported claims
2. Add few-shot examples and clarify prompt to keep answers on-topic
3. Increase chunk size in RAG pipeline to reduce context fragmentation

---

## 5. Regression Testing Strategy

### CI/CD Integration

**Câu 1: Khi nào chạy `run_regression()` trong production system?**
> Chạy ở mọi PR/merge vào main, mọi lần thay đổi prompt/system message, mọi lần đổi retrieval config (chunk size, top-k, embedding model), và trước mỗi lần demo/launch — bất kỳ thay đổi nào có thể ảnh hưởng tới output của agent.

**Câu 2: Threshold regression 0.05 có phù hợp domain của bạn không?**
> 0.05 hợp lý cho Relevance/Completeness, nhưng với Faithfulness — domain AI/RAG assistant (dễ bị hallucination khi trả lời sai kỹ thuật) — nên strict hơn (0.03), vì faithfulness là metric duy nhất đang ở mức "Significant Issues" (avg 0.41), một regression nhỏ thêm vào baseline đã yếu là rất nguy hiểm.

**Câu 3: Khi phát hiện regression — block deployment hay chỉ alert?**
> Block deploy nếu regression chạm Faithfulness hoặc xảy ra trên case Adversarial (A01–A03 dạng) — rủi ro hallucination/leak system prompt quá cao để chỉ alert. Với Relevance/Completeness trên case Easy/Medium không an toàn-critical, chỉ alert + theo dõi là đủ, tránh block deploy quá thường xuyên (cost của việc chặn release liên tục cũng là 1 trade-off thực).

**Câu 4: Eval pipeline nên chạy ở đâu trong CI/CD flow?**

```
Code change → [Run BenchmarkRunner trên golden dataset] → [generate_report + run_regression vs baseline] → [Gate: block nếu fail threshold/regression, alert nếu không] → Deploy
              (bước 1: offline eval)                        (bước 2: so baseline)                              (bước 3: quality gate)
```

---

## 6. Continuous Improvement Loop

Theo bài giảng: Evaluate → Analyze → Improve → Augment (add to benchmark) → lặp lại

**Sau lab hôm nay, 3 actions tiếp theo bạn sẽ làm để improve agent:**

| Priority | Action | Metric sẽ improve | Expected impact |
|----------|--------|-------------------|-----------------|
| 1 | Thêm self-verification step (check claim vs context) trước khi emit answer | Faithfulness | avg dự kiến 0.41 → 0.65+, giải quyết luôn 10 case mislabel `off_topic` |
| 2 | Thêm scope/intent classifier gate cho input trước generation | Faithfulness, Completeness (case Adversarial) | A01, A03 pass; giảm risk leak/hallucination cho out-of-scope query |
| 3 | Thêm few-shot conflict-handling examples cho Hard-tier prompt | Completeness, Relevance | H02 và các case Hard tương tự pass |

**Bạn sẽ thêm failure cases nào vào benchmark cho sprint tiếp theo?**
> 1. Câu hỏi multi-hop cần kết hợp 3+ chunk có thông tin bổ sung nhau (không mâu thuẫn nhưng rời rạc) — test completeness thực sự.
> 2. Câu hỏi yêu cầu trích nguồn (citation) — test xem agent có chỉ rõ claim nào từ context nào không.
> 3. Biến thể prompt injection tinh vi hơn A02 (nested instruction, multi-turn injection) — test độ bền guardrail.

---

## 7. Framework Reflection

**Framework bạn đã dùng trong lab:** Word-overlap heuristic (RAGAS-inspired)

**Nếu dùng trong production, bạn sẽ chọn framework nào? Tại sao?**
> RAGAS (real, LLM/embedding-based) — vì lab này đã lộ rõ giới hạn của word-overlap thuần lexical: answer đúng nội dung nhưng paraphrase khác wording context vẫn bị chấm Faithfulness thấp (10/20 case ở Part 3.2), và failure taxonomy 4-nhánh bỏ sót dải điểm biên 0.3–0.5. RAGAS dùng LLM/embedding để đánh giá theo *ý nghĩa* (semantic similarity) thay vì khớp từ, sẽ giảm false-negative loại này đáng kể.

| Tiêu chí | Lý do chọn |
|----------|------------|
| Focus phù hợp vì... | RAGAS có đủ bộ metric RAG-pipeline (Context Recall/Precision, Faithfulness, Answer Relevancy) đúng khớp với pipeline Recall→Precision→Faithfulness→Relevancy đã học, không cần tự code heuristic thay thế |
| CI/CD integration vì... | RAGAS có Python API trả score per-sample, dễ gọi trong test suite (`pytest`) hoặc GitHub Actions, set threshold + fail build giống `run_regression()` đã implement trong lab |
| Team workflow vì... | Output là score 0-1 + reasoning, dễ review trong PR (giống `generate_improvement_log`), và có thể swap LLM judge khi cần calibrate lại theo human feedback |
