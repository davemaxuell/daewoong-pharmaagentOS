import Image from "next/image";
import { LockKeyhole } from "lucide-react";
import { redirect } from "next/navigation";
import { signIn } from "@/auth";
import {
  isAuthConfigured,
  isGoogleAuthConfigured,
  isNaverAuthConfigured,
} from "@/auth";
import { SignInProviderButton } from "@/components/sign-in-provider-button";
import { safeAuthCallbackUrl } from "@/lib/auth-redirect";
import { getAuthenticatedPortalIdentity } from "@/lib/backend-auth";
import styles from "./sign-in.module.css";

type SignInPageProps = {
  searchParams: Promise<{
    callbackUrl?: string | string[];
    error?: string | string[];
  }>;
};

function errorCopy(value: string | string[] | undefined) {
  const error = Array.isArray(value) ? value[0] : value;
  if (!error) return null;
  if (error === "AccessDenied") {
    return "계정 정보를 확인할 수 없습니다. 이메일 제공 동의를 확인해 주세요.";
  }
  return "로그인을 완료하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

export default async function SignInPage({ searchParams }: SignInPageProps) {
  const params = await searchParams;
  const callbackUrl = safeAuthCallbackUrl(params.callbackUrl);
  const authConfigured = isAuthConfigured();
  const googleConfigured = isGoogleAuthConfigured();
  const naverConfigured = isNaverAuthConfigured();
  const error = errorCopy(params.error);

  if (authConfigured && await getAuthenticatedPortalIdentity()) {
    redirect(callbackUrl);
  }

  async function signInWithGoogle() {
    "use server";
    await signIn("google", { redirectTo: callbackUrl });
  }

  async function signInWithNaver() {
    "use server";
    await signIn("naver", { redirectTo: callbackUrl });
  }

  return (
    <main id="main-content" className={styles.page}>
      <div className={styles.orbit} aria-hidden="true" />
      <section className={styles.card} aria-labelledby="sign-in-title">
        <header className={styles.brand}>
          <Image
            src="/brand/daewoong-bio-logo.jpg"
            alt="대웅바이오"
            width={800}
            height={191}
            priority
            unoptimized
          />
          <span aria-hidden="true" />
          <p>FDA Intelligence</p>
        </header>

        <div className={styles.intro}>
          <p className={styles.eyebrow}>Welcome back</p>
          <h1 id="sign-in-title">계정으로 계속하세요</h1>
          <p>구글 또는 네이버 계정으로 간편하게 로그인하세요.</p>
        </div>

        {error ? (
          <div className={`${styles.notice} ${styles.errorNotice}`} role="alert">
            {error}
          </div>
        ) : null}

        {!authConfigured ? (
          <div className={styles.notice} role="status">
            로그인 연결을 준비하고 있습니다.
          </div>
        ) : null}

        <div className={styles.providers}>
          <form action={signInWithGoogle}>
            <SignInProviderButton
              provider="google"
              configured={googleConfigured}
              label="Google로 계속하기"
            />
          </form>
          <form action={signInWithNaver}>
            <SignInProviderButton
              provider="naver"
              configured={naverConfigured}
              label="네이버로 계속하기"
            />
          </form>
        </div>

        <footer className={styles.footer}>
          <LockKeyhole size={13} aria-hidden="true" />
          <span>안전한 OAuth 계정 연결</span>
        </footer>
      </section>

      <p className={styles.productLabel}>Daewoong Bio · FDA Drug Letter Intelligence</p>
    </main>
  );
}
