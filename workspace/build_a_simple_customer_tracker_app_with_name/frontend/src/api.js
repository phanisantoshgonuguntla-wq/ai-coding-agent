
const API_URL = "http://127.0.0.1:5000/api/items";

export async function getItems() {
    const response = await fetch(API_URL);

    if (!response.ok) {
        throw new Error("Could not load customers");
    }

    return response.json();
}

export async function addItem(item) {
    const response = await fetch(API_URL, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(item)
    });

    if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.error || "Could not add customer");
    }

    return response.json();
}
