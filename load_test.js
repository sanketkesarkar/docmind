import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";

const totalLatency = new Trend("total_latency_ms", true);
const embedLatency = new Trend("embed_latency_ms", true);
const searchLatency = new Trend("search_latency_ms", true);
const errorRate = new Rate("errors");

const DOCUMENT_ID = "203d13a8-5b1b-4268-b662-abf95954e07b";
const BASE_URL = "http://localhost:8000";

const QUESTIONS = [
  "What is Sankets work experience?",
  "What projects has Sanket built?",
  "What programming languages does Sanket know?",
  "What is Sankets education background?",
  "What companies has Sanket worked at?",
];

export const options = {
  scenarios: {
    load_test: {
      executor: "ramping-vus",
      startVUs: 1,
      stages: [
        { duration: "20s", target: 1 },
        { duration: "40s", target: 5 },
        { duration: "30s", target: 5 },
        { duration: "10s", target: 0 },
      ],
    },
  },
  thresholds: {
    total_latency_ms: ["p(50)<3000", "p(95)<6000"],
    errors: ["rate<0.05"],
  },
};

export default function () {
  const question = QUESTIONS[Math.floor(Math.random() * QUESTIONS.length)];

  const res = http.post(
    `${BASE_URL}/api/v1/query/retrieval-benchmark`,
    JSON.stringify({ question, document_id: DOCUMENT_ID }),
    {
      headers: { "Content-Type": "application/json" },
      timeout: "30s",
    }
  );

  const ok = check(res, {
    "status 200": (r) => r.status === 200,
    "has total_ms": (r) => {
      try { return JSON.parse(r.body).total_ms > 0; } catch { return false; }
    },
  });

  if (ok) {
    const body = JSON.parse(res.body);
    totalLatency.add(body.total_ms);
    embedLatency.add(body.embed_ms);
    searchLatency.add(body.search_ms);
  }

  errorRate.add(!ok);
  sleep(1);
}
