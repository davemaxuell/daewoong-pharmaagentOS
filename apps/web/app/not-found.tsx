import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { BilingualText } from "@/lib/i18n";

export default function NotFound() {
  return (
    <main id="main-content" className="state-page" tabIndex={-1}>
      <p className="eyebrow">
        <BilingualText en="404 · Record unavailable" ko="404 · 레코드를 찾을 수 없음" />
      </p>
      <h1>
        <BilingualText
          en="This Drug letter is not in the active corpus."
          ko="이 의약품 경고서한은 활성 코퍼스에 없습니다."
        />
      </h1>
      <p>
        <BilingualText
          en="It may be out of scope, unavailable, or awaiting deterministic Product verification."
          ko="범위 밖이거나, 사용할 수 없거나, 결정론적 Product 검증을 기다리는 중일 수 있습니다."
        />
      </p>
      <Link className="button button--primary" href="/drug-letters">
        <ArrowLeft size={16} aria-hidden="true" />
        <BilingualText en="Return to Drug Letters" ko="의약품 경고서한으로 돌아가기" />
      </Link>
    </main>
  );
}
