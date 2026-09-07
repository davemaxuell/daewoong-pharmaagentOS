"use client";

import Link from "next/link";
import { useState } from "react";
import { ArrowRight, GitBranch, Search, ShieldCheck } from "lucide-react";
import { agentDefinitions } from "@/lib/agent-workspace";
import { useI18n } from "@/lib/i18n";
import styles from "./agent-team.module.css";

export function AgentTeam() {
  const { text } = useI18n();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string>(agentDefinitions[0].key);
  const pick = (pair: readonly [string, string]) => text(pair[0], pair[1]);
  const agents = agentDefinitions.filter((agent) =>
    [...agent.name, ...agent.role, agent.key]
      .join(" ")
      .toLowerCase()
      .includes(query.toLowerCase().trim()),
  );
  const active = agents.find((agent) => agent.key === selected) ?? agents[0];
  return (
    <div className={styles.page}>
      <header>
        <div className={styles.kicker}>
          <GitBranch size={16} />
          {text("The specialist team", "전문 에이전트 팀")}
        </div>
        <h1>
          {text(
            "A clear role for every agent.",
            "각 에이전트의 역할을 명확하게.",
          )}
        </h1>
        <p>
          {text(
            "Explore the five versioned definitions behind regulatory impact review. These describe intended responsibilities; they do not indicate live execution readiness.",
            "규제 영향 검토를 구성하는 다섯 에이전트의 버전별 정의입니다. 예정된 역할을 설명하며 실시간 실행 준비 상태를 나타내지는 않습니다.",
          )}
        </p>
      </header>
      <div className={styles.toolbar}>
        <label>
          <Search size={16} />
          <span className="sr-only">
            {text("Search agents", "에이전트 검색")}
          </span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={text(
              "Find a specialist or responsibility",
              "전문가 또는 역할 검색",
            )}
            type="search"
          />
        </label>
        <span>
          {agents.length} {text("definitions", "개 정의")}
        </span>
      </div>
      <div className={styles.workspace}>
        <nav
          aria-label={text("Agent definitions", "에이전트 정의")}
          className={styles.roster}
        >
          {agents.map((agent, index) => (
            <button
              key={agent.key}
              type="button"
              aria-pressed={active?.key === agent.key}
              aria-controls="agent-detail"
              onClick={() => setSelected(agent.key)}
            >
              <span className={styles.avatar}>
                <GitBranch size={19} />
              </span>
              <span>
                <strong>{pick(agent.name)}</strong>
                <small>
                  v{agent.version} · {text("Definition", "정의")}
                </small>
              </span>
              <ArrowRight size={15} />
              <span className={styles.order}>{index + 1}</span>
            </button>
          ))}
          {!agents.length ? (
            <p className={styles.empty}>
              {text(
                "No agents match your search. Try evidence, knowledge, or verification.",
                "검색 결과가 없습니다. 근거, 지식, 검증 등의 키워드로 검색하세요.",
              )}
            </p>
          ) : null}
        </nav>
        {active ? (
          <section
            id="agent-detail"
            className={styles.detail}
            aria-live="polite"
          >
            <span className={styles.definition}>
              v{active.version} / {text("Agent definition", "에이전트 정의")}
            </span>
            <h2>{pick(active.name)}</h2>
            <p>{pick(active.role)}</p>
            <dl>
              <div>
                <dt>{text("Input", "입력")}</dt>
                <dd>{pick(active.input)}</dd>
              </div>
              <div>
                <dt>{text("Expected output", "예정된 출력")}</dt>
                <dd>{pick(active.output)}</dd>
              </div>
              <div>
                <dt>
                  {text("Tools in the review workflow", "검토 워크플로의 도구")}
                </dt>
                <dd>{pick(active.tools)}</dd>
              </div>
            </dl>
            <div className={styles.boundary}>
              <ShieldCheck size={20} />
              <p>
                {text(
                  "Agent outputs support a review. They do not determine compliance, approve a CAPA, or change a controlled document.",
                  "에이전트 결과는 검토를 지원합니다. 준수 여부를 판단하거나 CAPA를 승인하거나 관리 문서를 변경하지 않습니다.",
                )}
              </p>
            </div>
            <Link href="/dashboard">
              {text("Inspect the complete workflow", "전체 워크플로 살펴보기")}
              <ArrowRight size={16} />
            </Link>
            <details>
              <summary>{text("Definition identifier", "정의 식별자")}</summary>
              <code>
                {active.key}@{active.version}
              </code>
            </details>
          </section>
        ) : null}
      </div>
      <footer>
        <span>
          {text(
            "Execution and release status are tracked separately.",
            "실행 및 릴리스 상태는 별도로 관리됩니다.",
          )}
        </span>
        <Link href="/control-tower">
          {text("Open agent operations", "에이전트 운영 현황 열기")}
          <ArrowRight size={15} />
        </Link>
      </footer>
    </div>
  );
}
