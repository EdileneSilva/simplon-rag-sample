<script lang="ts">
  import { onMount } from 'svelte';
  import { env } from '$env/dynamic/public';
  import ChatHeader from '$lib/components/ChatHeader.svelte';
  import MessageList from '$lib/components/MessageList.svelte';
  import ChatInput from '$lib/components/ChatInput.svelte';
  import { createChatStore } from '$lib/stores/chat.svelte';

  const API_URL = env.PUBLIC_API_URL || 'http://localhost:8000';
  const chat = createChatStore(API_URL);

  onMount(() => {
    chat.init();
  });
</script>

<div class="flex h-[calc(100vh-3rem)] flex-col">
  <ChatHeader onReset={() => chat.reset()} />

  {#if chat.status === 'error' && chat.conversationId === null}
    <div class="my-auto flex flex-col items-center gap-3 text-center">
      <p class="text-brand-red">⚠️ Impossible de joindre l'API.</p>
      <button
        type="button"
        onclick={() => chat.init()}
        class="rounded-lg bg-brand-red px-4 py-2 font-medium text-white hover:opacity-90"
      >
        Réessayer
      </button>
    </div>
  {:else}
    <MessageList messages={chat.messages} status={chat.status} />

    {#if chat.status === 'error' && chat.conversationId !== null}
      <div
        class="mb-2 rounded-md border border-brand-red bg-brand-red/5 px-3 py-2 text-sm text-brand-red"
      >
        ⚠️ {chat.error?.message ?? "Erreur lors de l'envoi."}
      </div>
    {/if}

    <ChatInput
      disabled={chat.status === 'sending' || chat.status === 'connecting'}
      onSubmit={(text) => chat.send(text)}
    />
  {/if}
</div>
