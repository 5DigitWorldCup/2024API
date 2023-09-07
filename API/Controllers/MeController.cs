using API.Entities;
using API.Services.Interfaces;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace API.Controllers;

[ApiController]
[Route("api/[controller]")]
public class MeController : Controller
{
	private readonly IRegistrantService _registrantService;

	public MeController(IRegistrantService registrantService) { _registrantService = registrantService; }

	[Authorize]
	[HttpGet]
	public async Task<ActionResult<Registrant>> GetSelf()
	{
		if (HttpContext.User.Identity?.Name != null && long.TryParse(HttpContext.User.Identity.Name, out long osuId))
		{
			return Ok(await _registrantService.GetByOsuIdAsync(osuId));
		}

		return Unauthorized();
	}
}