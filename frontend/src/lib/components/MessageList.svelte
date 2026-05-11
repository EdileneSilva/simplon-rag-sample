<script lang="ts">
  import type { ChatStatus, Message } from '../types';
  import MessageBubble from './MessageBubble.svelte';
  import TypingIndicator from './TypingIndicator.svelte';

  interface Props {
    messages: Message[];
    status: ChatStatus;
  }

  let { messages, status }: Props = $props();
  let scrollEl: HTMLDivElement | null = $state(null);

  $effect(() => {
    void messages.length;
    void status;
    if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
  });
</script>

<div bind:this={scrollEl} class="flex-1 space-y-3 overflow-y-auto py-4">
  {#each messages as message (message.id)}
    <MessageBubble {message} />
  {/each}
  {#if status === 'sending'}
    <div class="flex justify-start">
      <div class="rounded-xl bg-surface-muted">
        <TypingIndicator />
      </div>
    </div>
  {/if}
  {#if messages.length === 0 && status === 'idle'}
    <p class="py-10 text-center text-sm text-brand-ink/60">
      Posez une première question pour démarrer la conversation.
    </p>
  {/if}
</div>
