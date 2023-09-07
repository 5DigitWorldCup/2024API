using API.Auth;
using API.Configurations;
using API.Entities;
using API.Services.Interfaces;
using Dapper;
using Npgsql;

namespace API.Services.Implementations;

public class SessionsService : ServiceBase<Session>, ISessionsService
{
	private readonly IDbCredentials _dbCredentials;
	private readonly ILogger _logger;
	
	public SessionsService(IDbCredentials dbCredentials, ILogger<SessionsService> logger) : base(dbCredentials, logger)
	{
		_dbCredentials = dbCredentials;
		_logger = logger;
	}

	public async Task<Registrant?> GetRegistrantAsync(string sessionToken)
	{
		using (var connection = new NpgsqlConnection(_dbCredentials.ConnectionString))
		{
			long? osuId = await connection.QueryFirstOrDefaultAsync<long?>("SELECT osu_id FROM sessions WHERE token = @Token", new { Token = sessionToken });
			if (osuId == null)
			{
				return null;
			}
			
			return await connection.QueryFirstOrDefaultAsync<Registrant?>("SELECT * FROM registrants WHERE osu_id = @OsuId", new { OsuId = osuId });
		}
	}

	public async Task<Session?> CreateAsync(long osuId)
	{
		using (var connection = new NpgsqlConnection(_dbCredentials.ConnectionString))
		{
			var session = new Session
			{
				OsuId = osuId,
				Token = TokenGenerationHelper.GenerateToken(),
				Expiration = DateTime.UtcNow.AddDays(7),
				Created = DateTime.UtcNow
			};

			try
			{
				await connection.ExecuteAsync("INSERT INTO sessions (osu_id, token, created, expiration) VALUES (@OsuId, @Token, @Created, @Expiration) " +
				                              "ON CONFLICT (osu_id) DO UPDATE SET token = @Token, created = @Created, expiration = @Expiration, updated = @Updated", new
				{
					OsuId = osuId,
					Token = session.Token,
					Created = session.Created,
					Expiration = session.Expiration,
					Updated = DateTime.UtcNow
				});
			}
			catch (Exception e)
			{
				_logger.LogError(e, "Failed to create session for osu id {OsuId}", osuId);
				return null;
			}
			
			return session;
		}
	}
}