$(function()
{


  $(".page_selector").change(function()
  {
    location.pathname = '/channels/' + (+$(this).val());
  });

  var starChannel = function()
  {
    var $t = $(this),
        channel = $t.data("stream"),
        starred = $t.is(".starred");

    if (channel)
    {
      var up = starred ? 'down' : 'up';
      var url = (['', 'vote', channel, up]).join('/');
      $.get(url, function(j)
      {
        if(j.hasOwnProperty("voted_for"))
        {
          var voted = j.voted_for;
          $t.parents('.row:first').find('.stars').text(j.stars);
          updateStarButton($t, voted);
        }
      });
    }
  };

  var updateStarButton = function($e, up)
  {
    if(up)
    {
        $e.addClass("starred")
        .data("starred", true)
        .attr("title", "You've starred this channel! That's awesome of you. Click again to remove star.")
        .find('.label')
        .text('Starred');
    }
    else
    {
        $e.removeClass("starred")
        .data("starred", false)
        .attr("title", "If you liked this channel, let others know by adding a star.")
        .find('.label')
        .text('Star');
    }
  };

  $('.star-button')
  .click(starChannel);
});
