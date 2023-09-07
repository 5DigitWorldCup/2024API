using API.Entities;

namespace API.Services.Interfaces;

public interface ISessionsService : IService<Session>
{
	Task<Registrant?> GetRegistrantAsync(string sessionToken);
	Task<Session?> CreateAsync(long osuId);
}