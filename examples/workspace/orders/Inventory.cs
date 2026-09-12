using System.Net.Http;

class Inventory
{
    public async Task Check()
    {
        var client = new HttpClient
        {
            BaseAddress = new Uri(config["Inventory:BaseUrl"])
        };
        await client.GetAsync("stock/42");
    }
}
