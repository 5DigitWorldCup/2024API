using API.Auth;
using API.Entities;
using API.Services.Interfaces;
using Microsoft.AspNetCore.Mvc;

namespace API.Controllers;

[ApiController]
[Route("api/[controller]")]
public class SessionsController : Controller
{
	private readonly ISessionsService _sessionsService;
	private readonly IConfiguration _configuration;
	private readonly ILogger<SessionsController> _logger;

	public SessionsController(ISessionsService sessionsService, IConfiguration configuration, ILogger<SessionsController> logger)
	{
		_sessionsService = sessionsService;
		_configuration = configuration;
		_logger = logger;
	}

	[HttpPost("create")]
	public async Task<ActionResult<Session>> CreateSessionAsync([FromQuery] long osuId, [FromQuery] string hash)
	{
		var secret = _configuration["Keys:SessionGenerationPhrase"];

		if (secret == null)
		{
			_logger.LogError("Keys:SessionGenerationPhrase is not set in configuration");
			return StatusCode(500, "Keys:SessionGenerationPhrase is not set in configuration!");
		}
		
		if (!HashUtilities.VerifySecret(secret, hash))
		{
			return Unauthorized();
		}
		
		var session = await _sessionsService.CreateAsync(osuId);
		if (session != null)
		{
			return Ok(session);
		}
		
		return StatusCode(500, $"Failed to create session for user {osuId} (internal error occurred)");
	}
}