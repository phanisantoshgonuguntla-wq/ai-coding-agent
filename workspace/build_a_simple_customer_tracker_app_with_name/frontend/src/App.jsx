import { useEffect, useState } from "react";
import { getItems, addItem } from "./api.js";

export default function App() {
    const [items, setItems] = useState([]);
    const [title, setTitle] = useState("");
    const [email, setEmail] = useState("");
    const [phone, setPhone] = useState("");
    const [description, setDescription] = useState("");
    const [search, setSearch] = useState("");
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
            setError("Name is required.");
            return;
        }

        try {
            await addItem({
                title,
                email,
                phone,
                description
            });

            setTitle("");
            setEmail("");
            setPhone("");
            setDescription("");
            await loadItems();
        } catch (err) {
            setError(err.message);
        }
    }

    useEffect(() => {
        loadItems();
    }, []);

    const filteredItems = items.filter((item) => {
        const searchableText = [
            item.title,
            item.email,
            item.phone,
            item.description
        ].join(" ").toLowerCase();

        return searchableText.includes(search.toLowerCase());
    });

    return (
        <main>
            <h1>Customer Tracker</h1>

            <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search customers"
            />

            <form onSubmit={handleSubmit}>
                <input
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="Name"
                />
                <input
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="Email"
                />
                <input
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                    placeholder="Phone"
                />
                <textarea
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder="Notes"
                />
                <button type="submit">Add</button>
            </form>

            {error && <p className="error">{error}</p>}

            <ul>
                {filteredItems.map((item) => (
                    <li key={item.id}>
                        <strong>{item.title}</strong>
                        {item.email && <span>{item.email}</span>}
                        {item.phone && <span>{item.phone}</span>}
                        {item.description && <p>{item.description}</p>}
                    </li>
                ))}
            </ul>
        </main>
    );
}
