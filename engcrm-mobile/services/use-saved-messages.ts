import { useCallback, useEffect, useState } from "react";
import { fetchSavedMessages, MessageWording, SavedMessage, saveMessage } from "./saved-messages";

export function useSavedMessages() {
  const [messages, setMessages] = useState<SavedMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const load = useCallback(() => fetchSavedMessages()
    .then((messages) => {
      setMessages(messages);
      setLoadFailed(false);
    })
    .catch(() => setLoadFailed(true))
    .finally(() => setLoading(false)), []);
  useEffect(() => { void load(); }, [load]);
  const reload = () => { setLoading(true); void load(); };
  const save = async (wording: MessageWording, existing?: SavedMessage) => {
    const stored = await saveMessage(wording, existing);
    setMessages((previous) => [stored, ...previous.filter((message) => message.id !== stored.id)]);
    return stored;
  };
  return { messages, loading, loadFailed, reload, save };
}
