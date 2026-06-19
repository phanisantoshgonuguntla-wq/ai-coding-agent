import { useEffect, useState } from "react";
import { getItems, addItem } from "./api.js";

export default function App() {
    const [items, setItems] = useState([]);
    const [title, setTitle] = useState("");

    async function loadItems() {
        const data = await getItems();
        setItems(data);
    }

    async function handleSubmit(event) {
        event.preventDefault();

        if (!title.trim()) {
            return;
        }

        await addItem(title);
        setTitle("");
        loadItems();
    }

    useEffect(() => {
        loadItems();
    }, []);

    return (
        <main>
            <h1>React + Flask App</h1>

            <form onSubmit={handleSubmit}>
                <input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="Add item"
                />
                <button type="submit">Add</button>
            </form>

            <ul>
                {items.map((item) => (
                    <li key={item.id}>{item.title}</li>
                ))}
            </ul>
        </main>
    );
}