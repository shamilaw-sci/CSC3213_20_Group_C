"use client";
import { useState, useRef, useEffect } from "react";
import { MessageCircle, X, Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useChat } from "@/hooks/useChat";

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const { turns, send, isPending } = useChat();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, isPending]);

  const submit = () => {
    const text = draft.trim();
    if (!text || isPending) return;
    send(text);
    setDraft("");
  };

  if (!open) {
    return (
      <Button
        onClick={() => setOpen(true)}
        size="icon"
        className="fixed bottom-6 right-6 h-14 w-14 rounded-full shadow-lg z-50"
        aria-label="Open assistant"
      >
        <MessageCircle className="h-6 w-6" />
      </Button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex h-[32rem] w-[22rem] flex-col rounded-lg border bg-background shadow-xl">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <span className="text-sm font-semibold">VFF Assistant</span>
        <Button variant="ghost" size="icon" className="h-7 w-7"
                onClick={() => setOpen(false)} aria-label="Close assistant">
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {turns.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Ask about finances, programs, or receivables. I can only see what
            your role has access to.
          </p>
        )}

        {turns.map((t, i) => (
          <div key={i} className={t.role === "user" ? "text-right" : "text-left"}>
            <div
              className={`inline-block max-w-[85%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
                t.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-foreground"
              }`}
            >
              {t.content}
            </div>
          </div>
        ))}

        {isPending && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Thinking…
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="flex gap-2 border-t p-3">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && submit()}
          placeholder="Ask a question…"
          disabled={isPending}
        />
        <Button size="icon" onClick={submit} disabled={isPending || !draft.trim()}>
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}