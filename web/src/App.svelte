<script lang="ts">
  import { getStatus, type Status } from './lib/api'
  import Nav from './lib/Nav.svelte'
  import Stepper from './lib/Stepper.svelte'
  import GraphView from './routes/GraphView.svelte'
  import PlanView from './routes/PlanView.svelte'
  import ProgressView from './routes/ProgressView.svelte'
  import TabsView from './routes/TabsView.svelte'
  import { type View } from './lib/views'

  let status: Status | null = $state(null)
  let current: View = $state('Tabs')

  $effect(() => {
    getStatus()
      .then((s) => (status = s))
      .catch(() => (status = null))
  })
</script>

<div id="app">
  <header>
    <span class="brand">dehoarder</span>
    <Stepper {status} />
    <Nav {current} onselect={(view) => (current = view)} />
  </header>

  <main>
    {#if current === 'Tabs'}
      <TabsView />
    {:else if current === 'Progress'}
      <ProgressView />
    {:else if current === 'Graph'}
      <GraphView />
    {:else if current === 'Plan'}
      <PlanView />
    {/if}
  </main>
</div>

<style>
  #app {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  header {
    display: flex;
    align-items: center;
    gap: 1.5rem;
    padding: 0.75rem 1.25rem;
    border-bottom: 1px solid var(--border);
  }

  .brand {
    font-weight: 600;
  }

  main {
    flex: 1;
    padding: 1.5rem;
  }
</style>
