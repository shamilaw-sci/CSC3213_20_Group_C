import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { ChatService, type ChatMessage } from '@/services/chat.service';
import { toast } from 'sonner';

export interface Turn {
  role: 'user' | 'assistant';
  content: string;
}

export function useChat() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [history, setHistory] = useState<ChatMessage[]>([]);

  const mutation = useMutation({
    mutationFn: (message: string) => ChatService.send(message, history),
    onSuccess: (data) => {
      setTurns((t) => [...t, { role: 'assistant', content: data.reply }]);
      setHistory(data.history);
    },
    onError: (error: any) => {
      setTurns((t) => t.slice(0, -1));
      toast.error(error?.response?.data?.detail || 'Assistant is unavailable');
    },
  });

  const send = (message: string) => {
    setTurns((t) => [...t, { role: 'user', content: message }]);
    mutation.mutate(message);
  };

  const reset = () => {
    setTurns([]);
    setHistory([]);
  };

  return { turns, send, reset, isPending: mutation.isPending };
}