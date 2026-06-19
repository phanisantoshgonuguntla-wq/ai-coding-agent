
import { useEffect, useState } from "react";
import { getItems, addItem } from "./api.js";

export default function App() {
    const [items, setItems] = useState([]);
    const [title, setTitle] = useState("");
    const [description, setDescription] = useState("");
    const [email, setEmail] = useState("");
    const [phone, setPhone] = useState("");
    const [search, setSearch] = useState("");

    async function loadItems() {
        const data = await getItems();
        setItems(data);
    }

    async function handleSubmit(event) {
        event.preventDefault();

        if (!title.trim()) {
            return;
        }

        await addItem({
            title,
            description,
            email,
            phone
        });

        setTitle("");
        setDescription("");
        setEmail("");
        setPhone("");

        await loadItems();
    }

    useEffect(() => {
        loadItems();
    }, []);

    const filteredItems = items.filter((item) => {
        const text = `${item.title || ""} ${item.description || ""} ${item.email || ""} ${item.phone || ""}`.toLowerCase();
        return text.includes(search.toLowerCase());
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
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    placeholder="Description"
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

                <button type="submit">Add</button>
            </form>

            <ul>
                {filteredItems.map((item) => (
                    <li key={item.id}>
                        <strong>{item.title}</strong>
                        <br />
                        {item.description}
                        <br />
                        {item.email}
                        <br />
                        {item.phone}
                    </li>
                ))}
            </ul>
        </main>
    );
}