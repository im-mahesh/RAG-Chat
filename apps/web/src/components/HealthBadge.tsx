import { useQuery } from '@tanstack/react-query'
import { fetchHealth } from '../api.ts'
import styles from './HealthBadge.module.css'

export function HealthBadge() {
  const { data, error, isPending } = useQuery({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: 10_000,
  })

  if (isPending) {
    return <span className={styles.badge}>API: checking…</span>
  }
  if (error) {
    return <span className={`${styles.badge} ${styles.error}`}>API: unreachable</span>
  }
  return <span className={`${styles.badge} ${styles.ok}`}>API: {data.status}</span>
}
