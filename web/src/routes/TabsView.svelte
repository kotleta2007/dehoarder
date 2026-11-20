<script lang="ts">
  import {
    createScan,
    createScanFromSnss,
    getBridgeStatus,
    getProfiles,
    listTabsFromExtension,
    type Profile,
    type ScanOut,
  } from '../lib/api'

  let bridgeConnected = $state<boolean | null>(null)
  let extensionId = $state<string | null>(null)
  let scanning = $state(false)
  let scanError = $state<string | null>(null)
  let scan = $state<ScanOut | null>(null)

  let profiles = $state<Profile[]>([])
  let selectedProfile = $state<string | null>(null)

  $effect(() => {
    getBridgeStatus()
      .then((s) => {
        bridgeConnected = s.connected
        extensionId = s.extension_id
      })
      .catch(() => {
        bridgeConnected = false
      })
  })

  $effect(() => {
    if (bridgeConnected !== false) return
    getProfiles()
      .then((p) => {
        profiles = p
        selectedProfile = p.find((x) => x.current)?.display_name ?? p[0]?.display_name ?? null
      })
      .catch(() => {
        profiles = []
      })
  })

  async function scanNow() {
    if (!extensionId) return
    scanning = true
    scanError = null
    try {
      const tabs = await listTabsFromExtension(extensionId)
      scan = await createScan(tabs)
    } catch (err) {
      scanError = err instanceof Error ? err.message : String(err)
    } finally {
      scanning = false
    }
  }

  async function readSessionFile() {
    scanning = true
    scanError = null
    try {
      scan = await createScanFromSnss(selectedProfile)
    } catch (err) {
      scanError = err instanceof Error ? err.message : String(err)
    } finally {
      scanning = false
    }
  }

  let domainCounts = $derived(
    scan
      ? Object.entries(
          scan.tabs.reduce<Record<string, number>>((acc, tab) => {
            acc[tab.domain] = (acc[tab.domain] ?? 0) + 1
            return acc
          }, {}),
        ).sort((a, b) => b[1] - a[1])
      : [],
  )
</script>

<section>
  <h1>Tabs</h1>

  {#if bridgeConnected === false}
    <div class="banner">
      <p><strong>Extension not detected.</strong> Load it once, then reload this page.</p>
      <ol>
        <li>Open <code>chromium://extensions</code>.</li>
        <li>Turn on <strong>Developer mode</strong>.</li>
        <li>
          Click <strong>Load unpacked</strong> and select the <code>extension/</code> directory.
        </li>
      </ol>
    </div>

    <div class="snss">
      <label for="profile-select">Profile</label>
      <select id="profile-select" bind:value={selectedProfile} disabled={profiles.length === 0}>
        {#each profiles as profile (profile.dir_name)}
          <option value={profile.display_name}>{profile.display_name}</option>
        {/each}
      </select>
      <button type="button" disabled={scanning || !selectedProfile} onclick={readSessionFile}>
        {scanning ? 'Reading…' : 'Read session file'}
      </button>
      <p class="hint">Read-only inventory. Closing tabs still needs the extension.</p>
    </div>
  {:else if bridgeConnected === true}
    <div class="banner ok">Extension connected{extensionId ? ` (${extensionId})` : ''}.</div>
    <button type="button" disabled={scanning} onclick={scanNow}>
      {scanning ? 'Scanning…' : 'Scan now'}
    </button>
  {/if}

  {#if scanError}
    <p class="error">{scanError}</p>
  {/if}

  {#if scan}
    <p>{scan.tab_count} tabs found.</p>
    <ul>
      {#each domainCounts as [domain, count] (domain)}
        <li>{domain} — {count}</li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .banner {
    padding: 0.75rem 1rem;
    border-radius: 6px;
    background: var(--bg-muted);
    margin-bottom: 1rem;
  }

  .banner.ok {
    color: var(--accent);
  }

  .snss {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    flex-wrap: wrap;
  }

  .hint {
    flex-basis: 100%;
    font-size: 0.85rem;
    color: var(--text);
    opacity: 0.75;
  }

  .error {
    color: #c0392b;
  }
</style>
