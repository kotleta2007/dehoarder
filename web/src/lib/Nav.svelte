<script lang="ts">
  import { VIEWS, type View } from './views'

  let { current, onselect }: { current: View; onselect: (view: View) => void } = $props()
</script>

<nav>
  {#each VIEWS as view (view)}
    <button type="button" class:active={view === current} onclick={() => onselect(view)}>
      {view}
    </button>
  {/each}
</nav>

<style>
  nav {
    display: flex;
    gap: 0.25rem;
  }

  button {
    font: inherit;
    padding: 0.4rem 0.9rem;
    border: none;
    border-radius: 6px;
    background: none;
    color: var(--text);
    cursor: pointer;
  }

  button:hover {
    background: var(--bg-muted);
  }

  button.active {
    background: var(--accent);
    color: var(--bg);
  }
</style>
