<script lang="ts">
  interface Props {
    disabled: boolean;
    onSubmit: (text: string) => void;
  }

  let { disabled, onSubmit }: Props = $props();
  let value = $state('');
  let textarea: HTMLTextAreaElement | null = $state(null);

  function submit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    value = '';
    if (textarea) textarea.style.height = 'auto';
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  function autosize() {
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }
</script>

<form
  class="flex items-end gap-2 border-t border-[color:var(--color-border-subtle)] bg-surface pt-3"
  onsubmit={(e) => {
    e.preventDefault();
    submit();
  }}
>
  <textarea
    bind:this={textarea}
    bind:value
    oninput={autosize}
    onkeydown={onKeydown}
    rows="1"
    placeholder="Posez votre question…"
    class="min-h-[44px] flex-1 resize-none rounded-lg border border-[color:var(--color-border-subtle)] bg-surface px-3 py-2 text-brand-ink outline-none focus:border-brand-coral"
  ></textarea>
  <button
    type="submit"
    disabled={disabled || !value.trim()}
    class="rounded-lg bg-brand-red px-4 py-2 font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
  >
    Envoyer
  </button>
</form>
