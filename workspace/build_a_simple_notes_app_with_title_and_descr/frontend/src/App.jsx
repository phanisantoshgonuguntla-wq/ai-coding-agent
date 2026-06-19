import { useEffect, useState } from "react";
import { addItem, getItems } from "./api.js";

export default function App() {
    const [items, setItems] = useState([]);
    const [title, setTitle] = useState("");
    const [description, setDescription] = useState("");
    const [error, setError] = useState("");

    async function loadItems() {
        try {
            const data = await getItems();
            setItems(data);
            setError("");
        } catch (err) {
            setError(err.message);
        }
    }

    async function handleSubmit(event) {
        event.preventDefault();
        setError("");

        if (!title.trim()) {
            setError("Title is required.");
            return;
        }

        try {
            await addItem({ title, description });
            setTitle("");
            setDescription("");
            await loadItems();
        } catch (err) {
            setError(err.message);
        }
    }

    useEffect(() => {
        loadItems();
    }, []);

    return (
        <main>
            <h1>Notes App</h1>

            <form onSubmit={handleSubmit}>
                <input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="Title"
                />
                <textarea
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder="Description"
                />
                <button type="submit">Add note</button>
            </form>

            {error && <p className="error">{error}</p>}

            <ul>
                {items.map((item) => (
                    <li key={item.id}>
                        <strong>{item.title}</strong>
                        {item.description && <p>{item.description}</p>}
                    </li>
                ))}
            </ul>
        </main>
    );
}