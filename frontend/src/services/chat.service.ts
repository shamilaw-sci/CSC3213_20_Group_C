import api from '@/lib/api-client';

export interface ChatMessage {
  role: string;
  content?: string;
  [key: string]: any;
}

export interface ChatResponse {
  reply: string;
  history: ChatMessage[];
}

export const ChatService = {
  async send(message: string, history: ChatMessage[]): Promise<ChatResponse> {
    const { data } = await api.post('/chat', { message, history });
    return data;
  },
};