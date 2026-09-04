import styles from "./page-loading.module.css";

export function PageLoading({ contained = false }: { contained?: boolean }) {
  return (
    <section
      className={`${styles.loader}${contained ? ` ${styles.contained}` : ""}`}
      role="status"
      aria-label="Loading"
      aria-busy="true"
    >
      <span className={styles.spinner} aria-hidden="true" />
    </section>
  );
}
