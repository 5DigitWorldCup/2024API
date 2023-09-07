using API.Configurations;
using API.Entities;
using API.Services.Interfaces;
using Dapper;
using Npgsql;

namespace API.Services.Implementations;

public class RegistrantService : ServiceBase<Registrant>, IRegistrantService
{
	private readonly IDbCredentials _dbCredentials;
	private readonly ILogger<RegistrantService> _logger;
	public RegistrantService(IDbCredentials dbCredentials, ILogger<RegistrantService> logger) : base(dbCredentials, logger)
	{
		_dbCredentials = dbCredentials;
		_logger = logger;
	}

	public async Task<Registrant> GetByOsuIdAsync(long osuId)
	{
		using(var connection = new NpgsqlConnection(_dbCredentials.ConnectionString))
		{
			return await connection.QueryFirstOrDefaultAsync<Registrant?>("SELECT * FROM registrants WHERE osu_id = @OsuId", new { OsuId = osuId });
		} 
	}
}