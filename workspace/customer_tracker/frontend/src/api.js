
const API_URL = "http://127.0.0.1:5000/api/items";

export async function getItems() {
    const response = await fetch(API_URL);
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

    return response.json();
}
