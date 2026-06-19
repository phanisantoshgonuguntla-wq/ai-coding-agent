using Microsoft.Data.Sqlite;

var builder = WebApplication.CreateBuilder(args);

builder.WebHost.UseUrls("http://127.0.0.1:5001");
builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy
            .WithOrigins("http://127.0.0.1:5174")
            .AllowAnyHeader()
            .AllowAnyMethod();
    });
});

var app = builder.Build();

app.UseCors();

const string connectionString = "Data Source=app.db";

static void InitDb(string connectionString)
{
    using var connection = new SqliteConnection(connectionString);
    connection.Open();

    using var command = connection.CreateCommand();
    command.CommandText = @"
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT
        );
    ";
    command.ExecuteNonQuery();
}

InitDb(connectionString);

app.MapGet("/api/items", () =>
{
    var items = new List<Item>();

    using var connection = new SqliteConnection(connectionString);
    connection.Open();

    using var command = connection.CreateCommand();
    command.CommandText = "SELECT id, title, description FROM items ORDER BY id DESC";

    using var reader = command.ExecuteReader();
    while (reader.Read())
    {
        items.Add(new Item(
            reader.GetInt32(0),
            reader.GetString(1),
            reader.IsDBNull(2) ? "" : reader.GetString(2)
        ));
    }

    return Results.Ok(items);
});

app.MapPost("/api/items", (ItemInput input) =>
{
    if (string.IsNullOrWhiteSpace(input.Title))
    {
        return Results.BadRequest(new { error = "title is required" });
    }

    using var connection = new SqliteConnection(connectionString);
    connection.Open();

    using var command = connection.CreateCommand();
    command.CommandText = @"
        INSERT INTO items (title, description)
        VALUES ($title, $description);
    ";
    command.Parameters.AddWithValue("$title", input.Title.Trim());
    command.Parameters.AddWithValue("$description", input.Description ?? "");
    command.ExecuteNonQuery();

    return Results.Created("/api/items", new { message = "item added" });
});

app.Run();

record Item(int Id, string Title, string Description);
record ItemInput(string Title, string? Description);