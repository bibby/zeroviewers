$(function()
{
    $("#language").change(function()
    {
        var lang = $(this).val();
        $.ajax({
            url: "/settings/language",
            type: "post",
            data: {
                "lang": lang
            },
            success: function()
            {
                location.reload();
            }
        });
    });

    $(document).tooltip();
});