"use client";

import googleIcon from "@iconify-icons/simple-icons/google";
import naverIcon from "@iconify-icons/simple-icons/naver";
import { Icon } from "@iconify/react";
import { LoaderCircle } from "lucide-react";
import { useFormStatus } from "react-dom";
import styles from "@/app/sign-in/sign-in.module.css";
import type { AuthProvider } from "@/lib/auth-types";

export function SignInProviderButton({
  provider,
  configured,
  label,
}: {
  provider: AuthProvider;
  configured: boolean;
  label: string;
}) {
  const { pending } = useFormStatus();
  const providerName = provider === "google" ? "Google" : "Naver";
  const providerIcon = provider === "google" ? googleIcon : naverIcon;

  return (
    <button
      className={`${styles.providerButton} ${provider === "google" ? styles.googleButton : styles.naverButton}`}
      type="submit"
      disabled={!configured || pending}
      aria-label={`${providerName} 계정으로 로그인 / Sign in with ${providerName}`}
    >
      <span className={styles.providerMark} aria-hidden="true">
        <Icon icon={providerIcon} width="20" height="20" />
      </span>
      <strong>{pending ? `${providerName} 연결 중…` : label}</strong>
      {!configured ? (
        <small>준비 중</small>
      ) : (
        <span className={styles.providerStatus} aria-hidden="true">
          {pending ? <LoaderCircle className={styles.spin} size={17} /> : null}
        </span>
      )}
    </button>
  );
}
