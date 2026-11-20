<script lang="ts">
  import {
    archiveScan,
    closeTabsInBrowser,
    createScan,
    createScanFromSnss,
    getBridgeStatus,
    getJob,
    getProfiles,
    getTabs,
    learnShop,
    listTabsFromExtension,
    reportClosed,
    setTabsDecision,
    startJob,
    type CloseSummary,
    type Profile,
    type ScanOut,
    type TabOut,
  } from '../lib/api'
  import { closeApproved } from '../lib/close'
  import { closeButtonState, groupTabs } from '../lib/review'

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

  let tabs = $state<TabOut[]>([])
  let classifying = $state(false)
  let classifyNote = $state<string | null>(null)
  let busy = $state(false)
  let actionError = $state<string | null>(null)

  const message = (err: unknown) => (err instanceof Error ? err.message : String(err))

  async function afterScan(result: ScanOut) {
    scan = result
    tabs = result.tabs
    if (result.classify_job_id !== null) {
      await waitForClassify(result.classify_job_id)
    }
  }

  async function waitForClassify(jobId: number) {
    if (!scan) return
    classifying = true
    classifyNote = null
    try {
      let job = await getJob(jobId)
      while (job.status === 'running') {
        await new Promise((resolve) => setTimeout(resolve, 500))
        job = await getJob(jobId)
      }
      if (job.status === 'failed') classifyNote = `Classification failed: ${job.error}`
      else if (typeof job.progress.warning === 'string') classifyNote = job.progress.warning
      tabs = await getTabs(scan.id)
    } catch (err) {
      classifyNote = message(err)
    } finally {
      classifying = false
    }
  }

  async function classifyNow() {
    try {
      const job = await startJob('classify')
      await waitForClassify(job.id)
    } catch (err) {
      classifyNote = message(err)
    }
  }

  async function scanNow() {
    if (!extensionId) return
    scanning = true
    scanError = null
    try {
      const chromeTabs = await listTabsFromExtension(extensionId)
      await afterScan(await createScan(chromeTabs))
    } catch (err) {
      scanError = message(err)
    } finally {
      scanning = false
    }
  }

  async function readSessionFile() {
    scanning = true
    scanError = null
    try {
      await afterScan(await createScanFromSnss(selectedProfile))
    } catch (err) {
      scanError = message(err)
    } finally {
      scanning = false
    }
  }

  /** Runs one review action, then reloads the scan's tabs from the server. */
  async function act(fn: () => Promise<unknown>) {
    if (!scan) return
    busy = true
    actionError = null
    try {
      await fn()
      tabs = await getTabs(scan.id)
    } catch (err) {
      actionError = message(err)
    } finally {
      busy = false
    }
  }

  const toggleShop = (shop: string, close: boolean) =>
    act(() => setTabsDecision(scan!.id, { shop }, close ? 'close' : 'keep'))

  const learnAndClose = (domain: string) =>
    act(async () => {
      const shop = await learnShop(domain)
      await setTabsDecision(scan!.id, { shop: shop.slug }, 'close')
    })

  const keepDomain = (domain: string) => act(() => setTabsDecision(scan!.id, { domain }, 'keep'))

  let closing = $state(false)
  let closeSummary = $state<CloseSummary | null>(null)

  async function closeNow() {
    const id = extensionId
    if (!scan || !id) return
    const scanId = scan.id
    closing = true
    closeSummary = null
    await act(async () => {
      closeSummary = await closeApproved(scanId, {
        archiveScan,
        listTabs: () => listTabsFromExtension(id),
        closeTabs: (ids) => closeTabsInBrowser(id, ids),
        reportClosed,
      })
    })
    closing = false
  }

  let review = $derived(groupTabs(tabs))
  let closeState = $derived(closeButtonState(tabs))
  // Session-file scans carry session ids, not live tab ids: never closable.
  let canClose = $derived(bridgeConnected === true && scan?.source === 'extension')
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

    {#if classifying}
      <p class="hint">Classifying tabs…</p>
    {:else if review.unclassified.length > 0}
      <p>
        {review.unclassified.length} tabs not classified yet.
        <button type="button" onclick={classifyNow}>Classify</button>
      </p>
    {/if}
    {#if classifyNote}
      <p class="error">{classifyNote}</p>
    {/if}
    {#if actionError}
      <p class="error">{actionError}</p>
    {/if}

    <h2>Known shops ({review.known.reduce((n, g) => n + g.tabs.length, 0)})</h2>
    <ul class="groups">
      {#each review.known as group (group.shop)}
        <li>
          <label>
            <input
              type="checkbox"
              checked={group.decision === 'close'}
              indeterminate={group.decision === 'mixed'}
              disabled={busy}
              onchange={(e) => toggleShop(group.shop, e.currentTarget.checked)}
            />
            {group.name} — {group.tabs.length}
          </label>
          <span class="hint">{group.decision === 'close' ? 'close' : 'keep open'}</span>
        </li>
      {/each}
    </ul>

    <h2>Looks like a book, unknown shop ({review.unknown.length} domains)</h2>
    <div class="cards">
      {#each review.unknown as group (group.domain)}
        <div class="card">
          <strong>{group.domain}</strong> — {group.tabs.length} tabs
          <ul>
            {#each group.tabs.slice(0, 3) as t (t.id)}
              <li><a href={t.url} target="_blank" rel="noreferrer">{t.title || t.url}</a></li>
            {/each}
          </ul>
          {#if group.decision === 'keep'}
            <p class="hint">Kept open.</p>
          {/if}
          <button type="button" disabled={busy} onclick={() => learnAndClose(group.domain)}>
            Learn &amp; close
          </button>
          <button
            type="button"
            disabled={busy || group.decision === 'keep'}
            onclick={() => keepDomain(group.domain)}
          >
            Keep
          </button>
        </div>
      {/each}
    </div>

    <details>
      <summary>Not a book ({review.notBook.length}) — always left open</summary>
      <ul>
        {#each review.notBook as t (t.id)}
          <li>{t.domain} — {t.title || t.url}</li>
        {/each}
      </ul>
    </details>

    <p>
      <button
        type="button"
        class="primary"
        disabled={closeState.disabled || !canClose || busy}
        onclick={closeNow}
      >
        {closing ? 'Closing…' : `Close approved (${closeState.count} tabs)`}
      </button>
      {#if !canClose}
        <span class="hint">Closing needs the extension and a scan made with it.</span>
      {:else if closeState.pending > 0}
        <span class="hint">{closeState.pending} tabs still need a decision.</span>
      {/if}
    </p>
    {#if closeSummary}
      <p class="banner ok">
        closed {closeSummary.closed} · failed {closeSummary.failed} · kept {closeSummary.kept}
      </p>
    {/if}
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

  .groups {
    list-style: none;
    padding: 0;
  }

  .groups li {
    display: flex;
    gap: 1rem;
    align-items: baseline;
    padding: 0.25rem 0;
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
    gap: 0.75rem;
  }

  .card {
    padding: 0.75rem;
    border-radius: 6px;
    background: var(--bg-muted);
  }

  .card ul {
    padding-left: 1.1rem;
    font-size: 0.9rem;
  }

  .primary {
    font-weight: 600;
  }
</style>
