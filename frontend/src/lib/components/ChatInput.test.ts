import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import ChatInput from './ChatInput.svelte';

describe('ChatInput', () => {
  it('submits on Enter and clears the textarea', async () => {
    const onSubmit = vi.fn();
    render(ChatInput, { props: { disabled: false, onSubmit } });
    const user = userEvent.setup();

    const textarea = screen.getByPlaceholderText(/posez votre question/i);
    await user.type(textarea, 'Bonjour');
    await user.keyboard('{Enter}');

    expect(onSubmit).toHaveBeenCalledWith('Bonjour');
    expect((textarea as HTMLTextAreaElement).value).toBe('');
  });

  it('does NOT submit on Shift+Enter', async () => {
    const onSubmit = vi.fn();
    render(ChatInput, { props: { disabled: false, onSubmit } });
    const user = userEvent.setup();

    const textarea = screen.getByPlaceholderText(/posez votre question/i);
    await user.type(textarea, 'Line1');
    await user.keyboard('{Shift>}{Enter}{/Shift}');

    expect(onSubmit).not.toHaveBeenCalled();
    expect((textarea as HTMLTextAreaElement).value).toContain('\n');
  });

  it('does not submit empty/whitespace content', async () => {
    const onSubmit = vi.fn();
    render(ChatInput, { props: { disabled: false, onSubmit } });
    const user = userEvent.setup();

    const textarea = screen.getByPlaceholderText(/posez votre question/i);
    await user.type(textarea, '   ');
    await user.keyboard('{Enter}');

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('disables the send button when disabled prop is true', () => {
    render(ChatInput, { props: { disabled: true, onSubmit: vi.fn() } });
    expect(screen.getByRole('button', { name: /envoyer/i })).toBeDisabled();
  });
});
