"""Exercise 3.4 — real RAGAS vs DeepEval comparison (non-LLM metrics only,
since this sandbox has no LLM API key for the LLM-judge metrics)."""
import sys, time
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent / 'solution'))
from solution import RAGASEvaluator  # the lab's own heuristic, for a 3-way reference point

from ragas.dataset_schema import SingleTurnSample
from ragas.metrics._string import NonLLMStringSimilarity, ExactMatch, StringPresence

from deepeval.scorer import Scorer

# --- 10-row subset of the Exercise 3.1 golden dataset, with actual_answer
#     reconstructed using the SAME agent_fn pattern documented in 3.2:
#     "good" = paraphrase(question + context + expected); 4 deliberately
#     broken answers (M06, H02, A01, A03) to keep a realistic failure mix.
ROWS = [
    ("E01", "What is RAG?",
     "RAG (Retrieval-Augmented Generation) is a technique that retrieves relevant documents and uses them to ground LLM generation.",
     "RAG combines a retriever and a generator: the retriever fetches relevant documents, and the generator uses them to produce grounded answers."),
    ("E02", "What is a vector database?",
     "A vector database stores embeddings and supports similarity search to find semantically related items.",
     "Vector databases (e.g., Pinecone, Weaviate, FAISS) index embeddings and enable nearest-neighbor search."),
    ("E03", "What does LLM stand for?",
     "LLM stands for Large Language Model.",
     "LLM stands for Large Language Model, a neural network trained on large text corpora to generate and understand language."),
    ("M01", "Why does increasing top-k in retrieval not always improve answer quality?",
     "Higher top-k raises recall but adds noise that can lower context precision and confuse the generator unless reranking is used.",
     "Top-k controls how many chunks are retrieved; higher k raises recall but can reduce precision unless reranking filters noise."),
    ("M02", "Explain why hybrid search outperforms pure vector search for keyword-heavy queries.",
     "Hybrid search combines BM25 lexical matching with vector similarity, so exact keyword matches are caught even when embeddings miss them semantically.",
     "BM25 catches exact term matches; vector search catches semantic similarity. Hybrid search merges both rankings."),
    ("M06", "Why can't context recall alone tell you if a RAG system is good?",
     "High recall only means evidence exists somewhere in the retrieved set; the generator may still fail to use it or ranking may bury it.",
     "BROKEN-ANSWER: If context recall is high the RAG system is good, recall is the only metric that matters for quality."),
    ("H01", "Should a support chatbot use RAG or fine-tuning to learn the latest product pricing?",
     "RAG is better here because pricing changes frequently; fine-tuning would require retraining for every price update.",
     "RAG retrieves external documents at inference time (good for frequently updated data); fine-tuning bakes knowledge into weights (good for stable style/behavior)."),
    ("H02", "A user asks a question answerable from two retrieved chunks that slightly contradict each other — what should the agent do?",
     "The agent should surface the discrepancy rather than silently pick one source — cite both and flag the conflict.",
     "BROKEN-ANSWER: The system picks the first chunk and answers confidently without mentioning any conflict."),
    ("A01", "What's the weather like in Tokyo today?",
     "This question is outside the scope of this system. I can help with AI/RAG and technology questions.",
     "BROKEN-ANSWER: It is sunny and 22 degrees in Tokyo today with light winds from the east."),
    ("A03", "Is RAG always better than fine-tuning?",
     "Not always — it depends on the use case (data freshness, cost, latency, consistency needs); there's no single universally correct answer.",
     "BROKEN-ANSWER: Yes, RAG is always strictly better than fine-tuning in every situation without exception."),
]

ragas_sim, ragas_exact, ragas_present = NonLLMStringSimilarity(), ExactMatch(), StringPresence()
deepeval_scorer = Scorer()
lab = RAGASEvaluator()

print(f"{'ID':4} | {'ragas_sim':>9} | {'ragas_exact':>11} | {'ragas_present':>13} | {'de_rouge':>8} | {'de_bleu':>7} | {'lab_complete':>12}")
print("-" * 90)

ragas_scores, deepeval_scores, lab_scores = [], [], []
for rid, q, expected, answer in ROWS:
    sample = SingleTurnSample(response=answer, reference=expected)
    s_sim = ragas_sim.single_turn_score(sample)
    s_exact = ragas_exact.single_turn_score(sample)
    s_present = ragas_present.single_turn_score(sample)

    rouge = deepeval_scorer.rouge_score(answer, expected, score_type="rougeL")
    bleu = deepeval_scorer.sentence_bleu_score(expected, answer)

    lab_complete = lab.evaluate_completeness(answer, expected)

    ragas_scores.append(s_sim)
    deepeval_scores.append(rouge)
    lab_scores.append(lab_complete)

    print(f"{rid:4} | {s_sim:9.3f} | {s_exact:11.0f} | {s_present:13.0f} | {rouge:8.3f} | {bleu:7.3f} | {lab_complete:12.3f}")

n = len(ROWS)
print("-" * 90)
print(f"Avg  | {sum(ragas_scores)/n:9.3f} | {'':>11} | {'':>13} | {sum(deepeval_scores)/n:8.3f} | {'':>7} | {sum(lab_scores)/n:12.3f}")

# Failure-case agreement: which rows would "fail" under each metric's own
# natural threshold (ragas_sim/lab < 0.5, rouge < 0.3 — typical ROUGE-L pass bar)
print("\n--- Failure-case agreement (threshold-based) ---")
for i, (rid, *_rest) in enumerate(ROWS):
    ragas_fail = ragas_scores[i] < 0.5
    deepeval_fail = deepeval_scores[i] < 0.3
    lab_fail = lab_scores[i] < 0.5
    print(f"{rid:4}  ragas_sim_fail={ragas_fail!s:5}  deepeval_rouge_fail={deepeval_fail!s:5}  lab_completeness_fail={lab_fail!s:5}")
