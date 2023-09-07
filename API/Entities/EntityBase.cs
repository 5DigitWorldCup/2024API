using Dapper;

namespace API.Entities;

public class EntityBase : IEntity
{
	[Key]
	[Column("id")]
	public int Id { get; set; }
	[Column("created")]
	public DateTime Created { get; set; }
	[Column("updated")]
	public DateTime? Updated { get; set; }
}