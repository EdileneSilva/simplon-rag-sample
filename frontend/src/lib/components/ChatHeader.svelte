<script lang="ts">
  interface Props {
    onReset: () => void;
  }
  let { onReset }: Props = $props();
</script>

<header
  class="flex items-center justify-between border-b border-[color:var(--color-border-subtle)] pb-4"
>
  <div>
    <h1 class="text-3xl font-bold tracking-wide text-brand-ink">RAG Sample</h1>
    <p class="text-sm font-medium text-brand-coral">Assistant IA</p>
  </div>
  <button
    type="button"
    onclick={onReset}
    class="rounded-lg border border-[color:var(--color-border-subtle)] px-3 py-2 text-sm font-medium text-brand-ink transition-colors hover:bg-surface-muted"
  >
    Nouvelle conversation
  </button>
</header>
