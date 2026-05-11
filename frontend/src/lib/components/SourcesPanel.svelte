<script lang="ts">
  let { sources }: { sources: string[] } = $props();
</script>

{#if sources.length > 0}
  <details
    class="mt-2 rounded-md border border-[color:var(--color-border-subtle)] px-3 py-2 text-sm"
  >
    <summary class="cursor-pointer select-none font-medium text-brand-ink">
      📎 Sources ({sources.length})
    </summary>
    <ul class="mt-2 space-y-1 text-xs text-brand-ink/70">
      {#each sources as id (id)}
        <li class="font-mono">{id}</li>
      {/each}
    </ul>
  </details>
{/if}
