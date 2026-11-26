<script lang="ts">
  import { getScans, type ScanSummary } from '../lib/api'

  let latest = $state<ScanSummary | null>(null)
  let error = $state<string | null>(null)

  $effect(() => {
    getScans()
      .then((scans) => {
        latest = scans[0] ?? null
      })
      .catch((err: unknown) => {
        error = err instanceof Error ? err.message : String(err)
      })
  })
</script>

<section>
  <h1>Progress</h1>

  {#if error}
    <p class="error">{error}</p>
  {:else if latest}
    <h2>Close</h2>
    <p>
      Scan #{latest.id} ({latest.tab_count} tabs, {new Date(latest.started_at).toLocaleString()})
    </p>
    <p class="summary">
      closed {latest.closed} · failed {latest.failed} · kept {latest.kept}
    </p>
  {:else}
    <p>No scan yet. Start from the Tabs view.</p>
  {/if}
</section>

<style>
  .summary {
    font-size: 1.1rem;
    font-weight: 600;
  }

  .error {
    color: #c0392b;
  }
</style>
