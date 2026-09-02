<script lang="ts">
  import type { Status } from './api'

  const STAGES = ['Scan', 'Review', 'Close', 'Process', 'Tag', 'Link', 'Plan'] as const

  let { status }: { status: Status | null } = $props()

  // Per-stage job tracking lands with the job chain in later phases; until
  // then this buckets the coarse counts /status already exposes.
  function currentStage(s: Status | null): (typeof STAGES)[number] {
    if (s === null || s.scans === 0) return 'Scan'
    if (s.books === 0) return 'Review'
    return 'Tag'
  }

  let current = $derived(currentStage(status))
</script>

<ol class="stepper">
  {#each STAGES as stage (stage)}
    <li class:current={stage === current}>{stage}</li>
  {/each}
</ol>

<style>
  .stepper {
    display: flex;
    gap: 0.4rem;
    list-style: none;
    margin: 0;
    padding: 0;
    font-size: 0.8rem;
  }

  .stepper li {
    padding: 0.15rem 0.6rem;
    border-radius: 999px;
    background: var(--bg-muted);
    color: var(--text);
  }

  .stepper li.current {
    background: var(--accent);
    color: var(--bg);
  }
</style>
