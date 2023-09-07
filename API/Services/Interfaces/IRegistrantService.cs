using API.Entities;

namespace API.Services.Interfaces;

public interface IRegistrantService : IService<Registrant>
{
	Task<Registrant?> GetByOsuIdAsync(long osuId);
}