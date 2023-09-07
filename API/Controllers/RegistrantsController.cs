using API.Entities;
using API.Services.Implementations;
using API.Services.Interfaces;
using Microsoft.AspNetCore.Mvc;

namespace API.Controllers;

[ApiController]
[Route("api/[controller]")]
public class RegistrantsController : CrudController<Registrant>
{
	public RegistrantsController(ILogger<RegistrantsController> logger, IRegistrantService service) : base(logger, service)
	{
		
	}
}