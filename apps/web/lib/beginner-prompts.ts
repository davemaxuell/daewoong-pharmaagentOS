// Stable task IDs keep user-written questions out of navigation URLs.
export const beginnerPrompts = [
  {
    id: "understand",
    title: { en: "Understand an FDA finding", ko: "FDA 지적 사항 이해하기" },
    prompt: {
      en: "Find FDA warning-letter examples about cleaning validation. Explain the main findings in plain language and show the source passages.",
      ko: "세척 밸리데이션 관련 FDA 경고서한 사례를 찾아주세요. 주요 지적 사항을 쉬운 말로 설명하고 원문 근거를 보여주세요.",
    },
  },
  {
    id: "compare",
    title: { en: "Compare similar cases", ko: "비슷한 사례 비교하기" },
    prompt: {
      en: "Find FDA warning letters about data integrity. Compare the common findings with source references, explaining unfamiliar terms.",
      ko: "데이터 무결성 관련 FDA 경고서한을 찾아주세요. 공통된 지적 사항을 원문 근거와 함께 비교하고 낯선 용어도 설명해주세요.",
    },
  },
  {
    id: "prepare",
    title: { en: "Prepare questions for my team", ko: "팀에서 확인할 질문 정리하기" },
    prompt: {
      en: "Using FDA warning-letter findings about quality oversight, suggest questions our quality team could review. Cite the sources and do not assume our company has the same issues.",
      ko: "품질 관리 감독 관련 FDA 경고서한 지적 사항을 바탕으로 우리 품질팀이 검토할 질문을 정리해주세요. 원문 근거를 제시하고 우리 회사에 같은 문제가 있다고 단정하지 마세요.",
    },
  },
] as const;
