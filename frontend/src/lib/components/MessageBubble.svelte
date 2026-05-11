<script lang="ts">
  import DOMPurify from 'dompurify';
  import { marked } from 'marked';
  import type { Message } from '../types';
  import SourcesPanel from './SourcesPanel.svelte';

  let { message }: { message: Message } = $props();

  const html = $derived(
    message.role === 'assistant'
      ? DOMPurify.sanitize(marked.parse(message.content, { async: false }) as string)
      : ''
  );

  const isUser = $derived(message.role === 'user');
</script>

<div class="flex w-full {isUser ? 'justify-end' : 'justify-start'}">
  <div
    class="max-w-[85%] rounded-xl px-4 py-3 {isUser
      ? 'bg-brand-red text-white'
      : 'bg-surface-muted text-brand-ink'}"
  >
    {#if isUser}
      <p class="whitespace-pre-wrap break-words">{message.content}</p>
    {:else}
      <div
        class="prose-sm max-w-none break-words [&_pre]:overflow-x-auto [&_pre]:rounded-md [&_pre]:bg-brand-ink/10 [&_pre]:p-2 [&_code]:font-mono"
      >
        <!-- eslint-disable-next-line svelte/no-at-html-tags -- HTML is sanitized via DOMPurify above -->
        {@html html}
      </div>
      <SourcesPanel sources={message.sources} />
    {/if}
  </div>
</div>
