const API_URL = "http://127.0.0.1:5000/todo";

export async function getItems() {
    const response = await fetch(API_URL);
    return response.json();
}

export async function addItem(title) {
    const response = await fetch(API_URL, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ title })
    });

    return response.json();
}