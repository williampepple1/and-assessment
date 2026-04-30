import React, { FormEvent, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import "./styles.css";

type Role = "user" | "assistant";

type ChatMessage = {
  role: Role;
  content: string;
};

type ChatResponse = {
  conversation_id?: string;
  content: string;
  tool_results?: Array<{
    name: string;
    content: string;
    is_error: boolean;
  }>;
};

const starterPrompts = [
  "Do you have wireless keyboards in stock?",
  "I want to place an order for a monitor.",
  "Can you help me find my order history?",
  "I am a returning customer and need to authenticate."
];

function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content:
        "Hi, I am Meridian's support assistant. I can help with product availability, orders, order history, and returning-customer authentication."
    }
  ]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const conversationHistory = useMemo(
    () => messages.filter((message) => message.role === "user" || message.role === "assistant"),
    [messages]
  );

  async function sendMessage(messageText: string) {
    const trimmed = messageText.trim();
    if (!trimmed || isLoading) return;

    const userMessage: ChatMessage = { role: "user", content: trimmed };
    setMessages((current) => [...current, userMessage]);
    setInput("");
    setError(null);
    setIsLoading(true);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: conversationId,
          message: trimmed,
          history: conversationHistory
        })
      });

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      const data = (await response.json()) as ChatResponse;
      if (data.conversation_id) {
        setConversationId(data.conversation_id);
      }
      setMessages((current) => [...current, { role: "assistant", content: data.content }]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Something went wrong.");
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: "I could not reach the support service. Please try again shortly."
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void sendMessage(input);
  }

  return (
    <main className="page">
      <section className="hero">
        <p className="eyebrow">Meridian Electronics</p>
        <h1>Customer Support Chatbot</h1>
        <p>
          A tool-grounded assistant for product availability, order placement, order history, and
          returning-customer authentication.
        </p>
      </section>

      <section className="chatShell" aria-label="Customer support chat">
        <div className="messages">
          {messages.map((message, index) => (
            <article key={`${message.role}-${index}`} className={`message ${message.role}`}>
              <span>{message.role === "assistant" ? "Assistant" : "You"}</span>
              <p>{message.content}</p>
            </article>
          ))}
          {isLoading && (
            <article className="message assistant">
              <span>Assistant</span>
              <p>Checking Meridian's systems...</p>
            </article>
          )}
        </div>

        <div className="prompts" aria-label="Example prompts">
          {starterPrompts.map((prompt) => (
            <button key={prompt} type="button" onClick={() => void sendMessage(prompt)}>
              {prompt}
            </button>
          ))}
        </div>

        <form className="composer" onSubmit={handleSubmit}>
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask about products, orders, or your account..."
            aria-label="Message"
          />
          <button type="submit" disabled={isLoading || !input.trim()}>
            Send
          </button>
        </form>
        {error && <p className="error">Error: {error}</p>}
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
